#!/usr/bin/env python3
"""
Pharma Intelligence - Consolidated Single-File Application (GitHub Ready)

Flask dashboard for Pharma Competitive Intelligence. All modules integrated:
- regulatory_sources: ClinicalTrials.gov, FDA Label, openFDA, EMA
- biohealth_news: Biopharma Dive, Fierce Pharma, Google News RSS
- pipeline_impact: Boehringer Ingelheim pipeline analysis
- article_extractor, summarizer

Requirements: pip install flask requests beautifulsoup4 newspaper3k openpyxl lxml
Run: python pharma_intelligence_app.py
URL: http://127.0.0.1:5001
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, Response
from newspaper import Article, ArticleException

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Embedded Clinical Pipeline Data ─────────────────────────────────────
CLINICAL_PIPELINE_JSON = {
    "source": "Clinical_Pipeline_Final.pdf",
    "company": "Boehringer Ingelheim",
    "as_of": "2025-10",
    "therapeutic_areas": [
        "Cardiovascular-Renal-Metabolic", "Eye Health", "Immunology",
        "Mental Health", "Oncology", "Respiratory"
    ],
    "legend": {
        "fast_track": "Fast Track Designation granted by the U.S. Food and Drug Administration",
        "combination": "Being investigated in combination with other therapies",
        "breakthrough": "Breakthrough Therapy/Device Designation or equivalent granted by US, EU or Japan",
        "partnership": "Anchored in external partnership or acquisition"
    },
    "assets": [
        {"id": "bi_1015550", "drug_name": "Nerandomilast", "drug_code": "BI 1015550",
         "mechanism": "PDE4B inhibitor", "phase": "registration",
         "indications": ["Idiopathic pulmonary fibrosis", "Progressive pulmonary fibrosis"],
         "therapeutic_area": "Respiratory", "flags": ["Fast Track"]},
        {"id": "bi_3972080", "drug_name": "CT-155", "drug_code": "BI 3972080",
         "mechanism": "Prescription digital therapeutic", "phase": "registration",
         "indications": ["Schizophrenia"], "therapeutic_area": "Mental Health", "flags": []},
        {"id": "bi_456906", "drug_name": "Survodutide", "drug_code": "BI 456906",
         "mechanism": "GLP1/GCGR agonist", "phase": "registration",
         "indications": ["Obesity", "Metabolic dysfunction-associated steatohepatitis"],
         "therapeutic_area": "Cardiovascular-Renal-Metabolic", "flags": []},
        {"id": "bi_1810631", "drug_name": "Zongertinib", "drug_code": "BI 1810631",
         "mechanism": "HER2 TKI", "phase": "registration",
         "indications": ["Non-small cell lung cancer"], "therapeutic_area": "Oncology", "flags": []},
        {"id": "bi_690517_empagliflozin", "drug_name": "Vicadrostat/Empagliflozin",
         "drug_code": "BI 690517/Empagliflozin",
         "mechanism": "Aldosterone synthase inhibitor/SGLT2 inhibitor", "phase": "registration",
         "indications": ["Cardiovascular risk reduction", "Heart failure with reduced ejection fraction",
                         "Chronic kidney disease", "Heart failure with preserved ejection fraction"],
         "therapeutic_area": "Cardiovascular-Renal-Metabolic", "flags": []},
        {"id": "bi_1291583", "drug_name": "Verducatib", "drug_code": "BI 1291583",
         "mechanism": "CatC inhibitor", "phase": "registration",
         "indications": ["Non-cystic fibrosis bronchiectasis"], "therapeutic_area": "Respiratory", "flags": []},
        {"id": "bi_1815368", "drug_name": "BI 1815368", "drug_code": "BI 1815368",
         "mechanism": "Vascular modulator", "phase": "phase_2",
         "indications": ["Diabetic macular edema"], "therapeutic_area": "Eye Health", "flags": []},
        {"id": "bi_764524", "drug_name": "BI 764524", "drug_code": "BI 764524",
         "mechanism": "Sema3A antibody", "phase": "phase_2",
         "indications": ["Diabetic retinopathy"], "therapeutic_area": "Eye Health", "flags": ["Fast Track"]},
        {"id": "bi_764198", "drug_name": "BI 764198", "drug_code": "BI 764198",
         "mechanism": "TRPC6 inhibitor", "phase": "phase_2",
         "indications": ["Focal segmental glomerulosclerosis"],
         "therapeutic_area": "Cardiovascular-Renal-Metabolic", "flags": []},
        {"id": "bi_764532", "drug_name": "Obrixtamig", "drug_code": "BI 764532",
         "mechanism": "DLL3/CD3 T-cell engager", "phase": "phase_2",
         "indications": ["Small-cell lung cancer", "Extra-pulmonary neuroendocrine carcinoma"],
         "therapeutic_area": "Oncology", "flags": []},
        {"id": "bi_685509", "drug_name": "Avenciguat", "drug_code": "BI 685509",
         "mechanism": "sGC activator", "phase": "phase_2",
         "indications": ["Systemic sclerosis"], "therapeutic_area": "Immunology", "flags": []},
        {"id": "bi_1819479", "drug_name": "BI 1819479", "drug_code": "BI 1819479",
         "mechanism": "Lysophospholipase inhibitor", "phase": "phase_2",
         "indications": ["Idiopathic/progressive pulmonary fibrosis"], "therapeutic_area": "Respiratory", "flags": []},
        {"id": "bi_771716", "drug_name": "BI 771716", "drug_code": "BI 771716",
         "mechanism": "Antibody fragment", "phase": "phase_2",
         "indications": ["Geographic atrophy"], "therapeutic_area": "Eye Health", "flags": []},
        {"id": "bi_770371", "drug_name": "BI 770371", "drug_code": "BI 770371",
         "mechanism": "SIRPa antagonist", "phase": "phase_2",
         "indications": ["Metabolic dysfunction-associated steatohepatitis"],
         "therapeutic_area": "Cardiovascular-Renal-Metabolic", "flags": []},
        {"id": "bi_1584862", "drug_name": "BI 1584862", "drug_code": "BI 1584862",
         "mechanism": "Phospholipid modulator", "phase": "phase_2",
         "indications": ["Geographic atrophy"], "therapeutic_area": "Eye Health", "flags": []},
        {"id": "bi_3032950", "drug_name": "BI 3032950", "drug_code": "BI 3032950",
         "mechanism": "TREM-1 antagonist", "phase": "phase_2",
         "indications": ["Ulcerative colitis"], "therapeutic_area": "Immunology", "flags": []},
        {"id": "bi_1015550_immunology", "drug_name": "Nerandomilast", "drug_code": "BI 1015550",
         "mechanism": "PDE4B inhibitor", "phase": "phase_2",
         "indications": ["Systemic sclerosis"], "therapeutic_area": "Immunology", "flags": []},
        {"id": "bi_690517_empagliflozin_ckd", "drug_name": "Vicadrostat/Empagliflozin",
         "drug_code": "BI 690517/Empagliflozin",
         "mechanism": "Aldosterone synthase inhibitor/SGLT2 inhibitor", "phase": "phase_2",
         "indications": ["Chronic kidney disease"], "therapeutic_area": "Cardiovascular-Renal-Metabolic", "flags": []},
        {"id": "bi_1810631_her2", "drug_name": "Zongertinib", "drug_code": "BI 1810631",
         "mechanism": "HER2 TKI", "phase": "phase_2",
         "indications": ["Advanced cancers with HER2 alterations"], "therapeutic_area": "Oncology", "flags": []},
    ]
}

# ── Article Extractor ───────────────────────────────────────────────────
@dataclass
class ExtractedArticle:
    url: str
    title: str
    text: str
    authors: list[str]
    publish_date: Optional[str]
    top_image: str
    success: bool
    error: Optional[str] = None


def extract_article(url: str, *, language: str = "en", timeout: int = 15) -> ExtractedArticle:
    try:
        article = Article(url, language=language, request_timeout=timeout)
        article.download()
        article.parse()
    except ArticleException as exc:
        return ExtractedArticle(url=url, title="", text="", authors=[], publish_date=None,
                                top_image="", success=False, error=str(exc))
    except Exception as exc:
        return ExtractedArticle(url=url, title="", text="", authors=[], publish_date=None,
                                top_image="", success=False, error=str(exc))
    if not article.text.strip():
        return ExtractedArticle(url=url, title="", text="", authors=[], publish_date=None,
                                top_image="", success=False, error="Article body is empty")
    pub_date = article.publish_date.isoformat() if article.publish_date else None
    return ExtractedArticle(url=url, title=article.title or "", text=article.text, authors=article.authors or [],
                            publish_date=pub_date, top_image=article.top_image or "", success=True)


# ── Summarizer (ArticleSummary for compatibility) ──────────────────────
@dataclass
class ArticleSummary:
    bullet_points: list[str]
    executive_summary: str
    drug_name: Optional[str]
    company: Optional[str]
    indication: Optional[str]
    regulatory_status: Optional[str]


# ── Regulatory Sources ─────────────────────────────────────────────────
_HEADERS = {"User-Agent": "shmo-pharma-intel/1.0"}
_TIMEOUT = 20


def fetch_clinical_trials(keywords: list[str], *, max_results: int = 100) -> list[dict]:
    url = "https://clinicaltrials.gov/api/v2/studies"
    articles = []
    for kw in keywords:
        params = {"query.cond": kw, "pageSize": max_results, "sort": "LastUpdatePostDate:desc",
                  "aggFilters": "phase:2 3",
                  "fields": "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,BriefSummary,LeadSponsorName,"
                            "StartDate,LastUpdatePostDate,PrimaryCompletionDate,Condition,InterventionName"}
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("ClinicalTrials.gov error for '%s': %s", kw, exc)
            continue
        for study in resp.json().get("studies", []):
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design = proto.get("designModule", {})
            desc = proto.get("descriptionModule", {})
            sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
            cond_mod = proto.get("conditionsModule", {})
            arms_mod = proto.get("armsInterventionsModule", {})
            nct_id = ident.get("nctId", "")
            phases = design.get("phases", [])
            phase_str = ", ".join(phases) if phases else "N/A"
            sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "Unknown")
            conditions = cond_mod.get("conditions", [])
            interventions = [i.get("name", "") for i in arms_mod.get("interventions", [])]
            last_update = (status_mod.get("lastUpdatePostDateStruct", {}).get("date", "") or
                          status_mod.get("startDateStruct", {}).get("date", ""))
            summary_text = desc.get("briefSummary", "")
            full_text = (f"Clinical Trial {nct_id}: {ident.get('officialTitle', '')}\nPhase: {phase_str}\n"
                         f"Sponsor: {sponsor}\nStatus: {status_mod.get('overallStatus', 'Unknown')}\n"
                         f"Conditions: {', '.join(conditions)}\nInterventions: {', '.join(interventions)}\n\n{summary_text}")
            articles.append({"title": ident.get("briefTitle", "Untitled"),
                             "link": f"https://clinicaltrials.gov/study/{nct_id}",
                             "source": "ClinicalTrials.gov", "published_date": last_update or "Unknown",
                             "keyword": kw, "full_text": full_text,
                             "meta": {"nct_id": nct_id, "phase": phase_str, "status": status_mod.get("overallStatus", "Unknown"),
                                      "sponsor": sponsor, "conditions": conditions, "interventions": interventions}})
    return articles


def _fda_drugsfda_query(kw: str, max_results: int) -> list[dict]:
    base = "https://api.fda.gov/drug/drugsfda.json"
    def _get(search_q: str):
        params = {"search": search_q, "sort": "submissions.submission_status_date:desc", "limit": max_results}
        resp = requests.get(base, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        return [] if resp.status_code == 404 else resp.json().get("results", [])
    try:
        exact_q = f'openfda.brand_name:"{kw}" openfda.generic_name:"{kw}" openfda.substance_name:"{kw}"'
        results = _get(exact_q)
        if not results:
            results = _get(f'"{kw}"')
        return results
    except requests.RequestException:
        return []


def fetch_fda_label(keywords: list[str], *, max_results: int = 100) -> list[dict]:
    base = "https://api.fda.gov/drug/label.json"
    articles = []
    for kw in keywords:
        params = {"search": f'indications_and_usage:"{kw}"', "sort": "effective_time:desc", "limit": max_results}
        try:
            resp = requests.get(base, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("openFDA label error for '%s': %s", kw, exc)
            continue
        for result in resp.json().get("results", []):
            openfda = result.get("openfda", {})
            brand_names = openfda.get("brand_name", [])
            generic_names = openfda.get("generic_name", [])
            manufacturer = openfda.get("manufacturer_name", [])
            pharm_class = openfda.get("pharm_class_epc", [])
            app_numbers = openfda.get("application_number", [])
            app_number = app_numbers[0] if app_numbers else ""
            indications = (result.get("indications_and_usage") or [""])[0]
            description = (result.get("description") or [""])[0]
            raw_et = result.get("effective_time", "")
            effective_date = f"{raw_et[:4]}-{raw_et[4:6]}-{raw_et[6:]}" if raw_et and len(raw_et) == 8 else raw_et or "Unknown"
            name_display = ", ".join(brand_names[:2]) or "Unknown"
            generic_display = ", ".join(generic_names[:1]) or "N/A"
            title = f"FDA Label: {name_display} ({generic_display}) — {kw}"
            full_text = (f"Brand Name(s): {', '.join(brand_names)}\nGeneric Name(s): {', '.join(generic_names)}\n"
                         f"Manufacturer: {', '.join(manufacturer)}\nPharmacological Class: {', '.join(pharm_class)}\n"
                         f"Application: {app_number}\nLabel Date: {effective_date}\n\n"
                         f"Indications and Usage:\n{indications[:1500]}\n\nDescription:\n{description[:500]}")
            link = (f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo="
                    f"{app_number.replace('NDA', '').replace('BLA', '')}") if app_number else "https://labels.fda.gov"
            articles.append({"title": title, "link": link, "source": "FDA Label", "published_date": effective_date,
                             "keyword": kw, "full_text": full_text,
                             "meta": {"brand_names": brand_names, "generic_names": generic_names,
                                      "pharm_class": pharm_class, "application_number": app_number,
                                      "effective_date": effective_date}})
    return articles


def fetch_fda_approvals(keywords: list[str], *, max_results: int = 100) -> list[dict]:
    articles = []
    for kw in keywords:
        for result in _fda_drugsfda_query(kw, max_results):
            openfda = result.get("openfda", {})
            brand_names = openfda.get("brand_name", [])
            generic_names = openfda.get("generic_name", [])
            manufacturer = openfda.get("manufacturer_name", ["Unknown"])
            pharm_class = openfda.get("pharm_class_epc", [])
            app_number = result.get("application_number", "")
            submissions = result.get("submissions", [])
            latest_sub = submissions[0] if submissions else {}
            sub_date = latest_sub.get("submission_status_date", "")
            sub_type = latest_sub.get("submission_type", "")
            sub_status = latest_sub.get("submission_status", "")
            review_priority = latest_sub.get("review_priority", "")
            products = result.get("products", [])
            product_lines = [f"  - {p.get('brand_name', '?')} ({p.get('dosage_form', '?')}, {p.get('route', '?')}) "
                            f"[{p.get('marketing_status', '?')}]" for p in products[:5]]
            display_date = f"{sub_date[:4]}-{sub_date[4:6]}-{sub_date[6:]}" if sub_date and len(sub_date) == 8 else sub_date or "Unknown"
            status_map = {"AP": "Approved", "TA": "Tentative Approval"}
            status_display = status_map.get(sub_status, sub_status)
            title = f"FDA {status_display}: {', '.join(brand_names[:2]) or 'Unknown'} ({', '.join(generic_names[:1]) or 'N/A'})"
            full_text = (f"Application: {app_number}\nBrand Name(s): {', '.join(brand_names)}\n"
                         f"Generic Name(s): {', '.join(generic_names)}\nManufacturer: {', '.join(manufacturer)}\n"
                         f"Pharmacological Class: {', '.join(pharm_class)}\n"
                         f"Latest Submission: {sub_type} — {status_display}\nReview Priority: {review_priority}\n"
                         f"Date: {display_date}\n\nProducts:\n" + "\n".join(product_lines))
            link = f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_number.replace('NDA', '').replace('BLA', '')}"
            articles.append({"title": title, "link": link, "source": "openFDA", "published_date": display_date,
                             "keyword": kw, "full_text": full_text,
                             "meta": {"application_number": app_number, "brand_names": brand_names,
                                      "generic_names": generic_names, "manufacturer": manufacturer,
                                      "submission_status": status_display, "review_priority": review_priority}})
    return articles


def fetch_ema_medicines(keywords: list[str], *, max_results: int = 100) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        logger.warning("EMA: openpyxl not installed — skipping EMA source")
        return []
    _EMA_XLSX_URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
    _cache_dir = Path(__file__).resolve().parent / ".cache"
    _cache_file = _cache_dir / "ema_medicines.xlsx"
    _cache_ttl = 86400
    _cache_dir.mkdir(exist_ok=True)
    if _cache_file.exists() and (time.time() - _cache_file.stat().st_mtime) < _cache_ttl:
        pass
    else:
        try:
            resp = requests.get(_EMA_XLSX_URL, headers=_HEADERS, timeout=60)
            resp.raise_for_status()
            _cache_file.write_bytes(resp.content)
        except requests.RequestException as exc:
            logger.warning("EMA: download failed — %s", exc)
            return []
    wb = openpyxl.load_workbook(_cache_file, read_only=True, data_only=True)
    ws = wb.active
    _COL = {"category": 0, "name": 1, "product_number": 2, "status": 3, "authorisation_date": 4,
            "inn": 6, "active_substance": 7, "therapeutic_area": 8, "atc_code": 11, "pharma_group": 13}
    _STOP = {"and", "or", "the", "of", "in", "for", "with", "a", "an", "to"}
    _SYNONYMS = {"kidney": ["renal"], "renal": ["kidney"], "heart": ["cardiac", "cardiovascular"],
                 "obesity": ["overweight", "obese"], "diabetes": ["diabetic", "glycemic"],
                 "cancer": ["neoplasm", "tumor", "carcinoma"], "ckd": ["chronic kidney", "renal"]}
    articles = []
    for kw in keywords:
        kw_lower = kw.lower()
        raw_words = [w for w in kw_lower.split() if w not in _STOP and len(w) > 2]
        expanded_words = [[w] + _SYNONYMS.get(w, []) for w in raw_words]
        matched = 0
        for row in ws.iter_rows(min_row=11, values_only=True):
            if matched >= max_results:
                break
            category = str(row[_COL["category"]] or "")
            if category != "Human":
                continue
            name = str(row[_COL["name"]] or "")
            inn = str(row[_COL["inn"]] or "")
            active = str(row[_COL["active_substance"]] or "")
            area = str(row[_COL["therapeutic_area"]] or "")
            status = str(row[_COL["status"]] or "")
            prod_num = str(row[_COL["product_number"]] or "")
            pharma_grp = str(row[_COL["pharma_group"]] or "")
            auth_date_raw = row[_COL["authorisation_date"]]
            auth_date = auth_date_raw.strftime("%Y-%m-%d") if auth_date_raw and hasattr(auth_date_raw, 'strftime') else str(auth_date_raw) if auth_date_raw else "Unknown"
            searchable = f"{name} {inn} {active} {area}".lower()
            phrase_match = kw_lower in searchable
            words_match = bool(expanded_words) and all(any(v in searchable for v in variants) for variants in expanded_words)
            if not (phrase_match or words_match):
                continue
            matched += 1
            link = f"https://www.ema.europa.eu/en/medicines/human/EPAR/{name.lower().replace(' ', '-').split('(')[0].strip('-')}"
            title = f"EMA: {name} ({inn})" if inn else f"EMA: {name}"
            full_text = (f"Medicine: {name}\nINN: {inn}\nActive Substance: {active}\nTherapeutic Area: {area}\n"
                         f"Pharmacotherapeutic Group: {pharma_grp}\nStatus: {status}\nDate: {auth_date}\nProduct: {prod_num}\n")
            articles.append({"title": title, "link": link, "source": "EMA", "published_date": auth_date,
                             "keyword": kw, "full_text": full_text,
                             "meta": {"medicine_name": name, "inn": inn, "active_substance": active,
                                      "status": status, "therapeutic_area": area, "product_number": prod_num,
                                      "authorisation_date": auth_date}})
    wb.close()
    def _sort_key(a):
        try:
            return int(a.get("meta", {}).get("product_number", "").split("/")[-1])
        except (ValueError, IndexError):
            return 0
    articles.sort(key=_sort_key, reverse=True)
    return articles


def fetch_all_sources(keywords: list[str], *, max_per_source: int = 100,
                      sources: Optional[list[str]] = None) -> list[dict]:
    enabled = set(sources or ["clinicaltrials", "fda", "fda_label", "ema"])
    all_results = []
    if "clinicaltrials" in enabled:
        all_results.extend(fetch_clinical_trials(keywords, max_results=max_per_source))
    if "fda" in enabled:
        all_results.extend(fetch_fda_approvals(keywords, max_results=max_per_source))
    if "fda_label" in enabled:
        all_results.extend(fetch_fda_label(keywords, max_results=max_per_source))
    if "ema" in enabled:
        all_results.extend(fetch_ema_medicines(keywords, max_results=max_per_source))
    return all_results


# ── Biohealth News ──────────────────────────────────────────────────────
_BH_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_TARGET_SOURCE_DOMAINS = {"biopharmadive.com", "fiercepharma.com", "endpts.com", "endpoints.news",
                          "statnews.com", "bioworld.com", "edaily.co.kr", "etoday.co.kr",
                          "dailypharm.com", "medipana.com", "yakup.com"}
_DOMAIN_TO_SOURCE = {"biopharmadive.com": "Biopharma Dive", "fiercepharma.com": "Fierce Pharma",
                     "endpts.com": "Endpoints News", "endpoints.news": "Endpoints News",
                     "statnews.com": "STAT News", "bioworld.com": "BioWorld",
                     "edaily.co.kr": "이데일리", "etoday.co.kr": "이투데이", "dailypharm.com": "데일리팜",
                     "medipana.com": "메디파나", "yakup.com": "약업신문"}


def _safe_get(url: str, **kwargs) -> Optional[requests.Response]:
    req_headers = {**_BH_HEADERS, **kwargs.pop("headers", {})}
    req_timeout = kwargs.pop("timeout", 20)
    try:
        return requests.get(url, headers=req_headers, timeout=req_timeout, **kwargs)
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


def _extract_domain(url: str) -> Optional[str]:
    try:
        host = urlparse(url).netloc or urlparse(url).path
        return host.lower().replace("www.", "").split(":")[0] if host else None
    except Exception:
        return None


def _is_target_source(link: str) -> bool:
    domain = _extract_domain(link)
    return any(t in (domain or "") for t in _TARGET_SOURCE_DOMAINS)


def _source_from_link(link: str) -> str:
    domain = _extract_domain(link)
    for d, name in _DOMAIN_TO_SOURCE.items():
        if d in (domain or ""):
            return name
    return "Pharma News"


def fetch_google_news_rss(query: str, source_name: str, max_results: int = 10,
                         filter_target_sources: bool = False) -> list[dict]:
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    resp = _safe_get(rss_url, headers={**_BH_HEADERS, "Accept-Encoding": "gzip, deflate"})
    if not resp:
        return []
    try:
        soup = BeautifulSoup(resp.content, "lxml-xml")
        articles = []
        for item in soup.select("item"):
            title_el, link_el, pub_date_el, source_el = item.select_one("title"), item.select_one("link"), item.select_one("pubDate"), item.select_one("source")
            if not title_el or not link_el:
                continue
            link = link_el.get_text(strip=True)
            source_url = source_el.get("url", "") if source_el else ""
            check_url = source_url or link
            if filter_target_sources and not _is_target_source(check_url):
                continue
            actual_source = _source_from_link(check_url) if filter_target_sources else (source_el.get_text(strip=True) if source_el else source_name)
            articles.append({"title": title_el.get_text(strip=True), "link": link, "source": actual_source,
                            "published_date": pub_date_el.get_text(strip=True)[:16] if pub_date_el else "Recent", "snippet": ""})
            if len(articles) >= max_results:
                break
        return articles
    except Exception as e:
        logger.warning("Google News RSS parse error: %s", e)
        return []


def fetch_google_news_korean(query: str, max_results: int = 10, filter_target_sources: bool = False) -> list[dict]:
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    resp = _safe_get(rss_url, headers={**_BH_HEADERS, "Accept-Encoding": "gzip, deflate"})
    if not resp:
        return []
    try:
        soup = BeautifulSoup(resp.content, "lxml-xml")
        articles = []
        for item in soup.select("item"):
            title_el, link_el, pub_date_el, source_el = item.select_one("title"), item.select_one("link"), item.select_one("pubDate"), item.select_one("source")
            if not title_el or not link_el:
                continue
            link = link_el.get_text(strip=True)
            source_url = source_el.get("url", "") if source_el else ""
            check_url = source_url or link
            if filter_target_sources and not _is_target_source(check_url):
                continue
            display_source = _source_from_link(check_url) if filter_target_sources else (source_el.get_text(strip=True) if source_el else "Korean News")
            articles.append({"title": title_el.get_text(strip=True), "link": link, "source": display_source,
                            "published_date": pub_date_el.get_text(strip=True)[:16] if pub_date_el else "Recent", "snippet": ""})
            if len(articles) >= max_results:
                break
        return articles
    except Exception as e:
        logger.warning("Google News Korean parse error: %s", e)
        return []


def _article_matches_keywords(a: dict, kw_lower: list[str]) -> bool:
    combined = f"{(a.get('title') or '')} {(a.get('snippet') or '')} {(a.get('full_text') or '')}".lower()
    return any(kw in combined for kw in kw_lower)


def enrich_articles_with_content(articles: list[dict], max_articles: int = 15, timeout: int = 10) -> None:
    to_fetch = [a for a in articles if not a.get("full_text")][:max_articles]
    def fetch_one(a):
        link = a.get("link", "")
        if link:
            result = extract_article(link, timeout=timeout)
            if result.success and result.text:
                a["full_text"] = result.text[:8000]
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(fetch_one, to_fetch))


def filter_articles_by_keywords(articles: list[dict], keywords: list[str], *,
                                enrich_with_content: bool = True, max_enrich: int = 15) -> list[dict]:
    if not keywords:
        return articles
    kw_lower = [k.strip().lower() for k in keywords if k.strip()]
    if not kw_lower:
        return articles
    matched = [a for a in articles if _article_matches_keywords(a, kw_lower)]
    unmatched = [a for a in articles if a not in matched]
    if enrich_with_content and unmatched:
        enrich_articles_with_content(unmatched, max_articles=max_enrich, timeout=10)
        newly_matched = [a for a in unmatched if _article_matches_keywords(a, kw_lower)]
        matched = matched + newly_matched
    return matched


def fetch_biohealth_news_by_keywords(keywords: list[str], max_results: int = 15,
                                     enrich_with_content: bool = True) -> tuple[list[dict], str]:
    if not keywords:
        return [], ""
    kw_clean = [k.strip() for k in keywords if k.strip()]
    if not kw_clean:
        return [], ""
    all_articles, seen_titles = [], set()
    for kw in kw_clean:
        for query in [kw, f"{kw} drug pharmaceutical", f"{kw} biotech"]:
            for a in fetch_google_news_rss(query, "Pharma News", max_results=max_results, filter_target_sources=False):
                title_key = (a["title"] or "")[:80].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    all_articles.append(a)
            if len(all_articles) >= max_results * 2:
                break
        if len(all_articles) >= max_results * 2:
            break
    if not all_articles:
        return [], ""
    enrich_articles_with_content(all_articles, max_articles=max_results, timeout=10)
    filtered = filter_articles_by_keywords(all_articles, kw_clean, enrich_with_content=False, max_enrich=0)[:max_results]
    for a in filtered:
        text = a.get("full_text") or a.get("snippet") or ""
        a["summary"] = (text[:250] + "..." if len(text) > 250 else text).strip() or a.get("title", "")
    overall_summary = "Key articles:\n" + "\n".join(f"• {a['title']}" for a in filtered[:10]) if filtered else ""
    return filtered, overall_summary


def fetch_biopharma_dive(max_results: int = 10) -> list[dict]:
    rss_url = "https://www.biopharmadive.com/feeds/news"
    resp = _safe_get(rss_url, headers={**_BH_HEADERS, "Accept-Encoding": "gzip, deflate"})
    if resp and (b"<rss" in resp.content[:500] or b"<item>" in resp.content[:2000]):
        try:
            soup = BeautifulSoup(resp.content, "lxml-xml")
            articles = []
            for item in soup.select("item")[:max_results]:
                title_el, link_el, pub_date_el = item.select_one("title"), item.select_one("link"), item.select_one("pubDate")
                if not title_el or not link_el:
                    continue
                href = link_el.get_text(strip=True)
                if "/spons/" in href:
                    continue
                title = title_el.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                articles.append({"title": title, "link": href, "source": "Biopharma Dive",
                                "published_date": pub_date_el.get_text(strip=True)[:16] if pub_date_el else "Recent", "snippet": ""})
            if articles:
                return articles
        except Exception as e:
            logger.warning("Biopharma Dive RSS parse error: %s", e)
    url = "https://www.biopharmadive.com/news/"
    resp = _safe_get(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    articles, seen = [], set()
    for a_tag in soup.select("a[href*='/news/']"):
        if len(articles) >= max_results:
            break
        href = a_tag.get("href", "")
        if "/topic/" in href or "/spons/" in href or href in seen:
            continue
        link = urljoin(url, href)
        title = a_tag.get_text(strip=True)
        if not title or len(title) < 15:
            continue
        seen.add(link)
        articles.append({"title": title, "link": link, "source": "Biopharma Dive", "published_date": "Recent", "snippet": ""})
    return articles[:max_results]


def fetch_fierce_pharma(max_results: int = 10) -> list[dict]:
    url = "https://www.fiercepharma.com/pharma"
    resp = _safe_get(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    articles, seen = [], set()
    for a_tag in soup.select("a[href*='/pharma/'], a[href*='/article/']"):
        if len(articles) >= max_results:
            break
        href = a_tag.get("href", "")
        if not href or href in seen or "/company/" in href or "/topic/" in href:
            continue
        title = a_tag.get_text(strip=True)
        if not title or len(title) < 15:
            continue
        link = urljoin(url, href) if not href.startswith("http") else href
        seen.add(href)
        articles.append({"title": title, "link": link, "source": "Fierce Pharma", "published_date": "Recent", "snippet": ""})
    return articles


def fetch_all_biohealth_news(max_per_source: int = 10) -> list[dict]:
    fetchers = [
        ("Biopharma Dive", fetch_biopharma_dive),
        ("Fierce Pharma", fetch_fierce_pharma),
    ]
    all_articles = []
    for source_name, fetcher in fetchers:
        try:
            articles = fetcher(max_results=max_per_source)
            if articles:
                all_articles.extend(articles)
        except Exception as exc:
            logger.warning("Error fetching from %s: %s", source_name, exc)
    if len(all_articles) < max_per_source * 2:
        for query in ["site:biopharmadive.com pharmaceutical", "site:fiercepharma.com drug"]:
            all_articles.extend(fetch_google_news_rss(query, "Pharma News", max_results=5, filter_target_sources=True))
    seen_titles = set()
    unique = []
    for a in all_articles:
        key = a["title"][:50].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)
    return unique


def fetch_top_biohealth_news(total: int = 10) -> list[dict]:
    per_source = max(3, (total + 5) // 10)
    all_articles = fetch_all_biohealth_news(max_per_source=per_source)
    if not all_articles:
        return []
    by_source = defaultdict(list)
    for a in all_articles:
        by_source[a["source"]].append(a)
    priority = ["Biopharma Dive", "Fierce Pharma"] + [s for s in by_source if s not in ["Biopharma Dive", "Fierce Pharma"]]
    result = []
    while len(result) < total:
        added = False
        for src in priority:
            if by_source[src]:
                result.append(by_source[src].pop(0))
                added = True
                if len(result) >= total:
                    break
        if not added:
            break
    return result[:total]


# ── Pipeline Impact ────────────────────────────────────────────────────
_COMPETITOR_MAP = {
    "semaglutide": {"ozempic", "wegovy", "rybelsus"}, "tirzepatide": {"mounjaro", "zepbound"},
    "dapagliflozin": {"farxiga"}, "empagliflozin": {"jardiance"}, "finerenone": {"kerendia"},
    "glp-1": {"glp1", "glp 1"}, "sglt2": {"sglt 2", "sglt-2"},
}
_MECHANISM_TO_ASSETS = {
    "glp1": ["bi_456906"], "glp-1": ["bi_456906"], "sglt2": ["bi_690517_empagliflozin", "bi_690517_empagliflozin_ckd"],
    "ckd": ["bi_690517_empagliflozin", "bi_690517_empagliflozin_ckd", "bi_764198"],
    "obesity": ["bi_456906"], "her2": ["bi_1810631", "bi_1810631_her2"],
}


def _extract_text(article: dict) -> str:
    parts = []
    if article.get("title"):
        parts.append(article["title"])
    if article.get("full_text"):
        parts.append(article["full_text"])
    if article.get("summary"):
        s = article["summary"]
        if isinstance(s, dict):
            parts.extend(s.get("bullet_points", []) or [])
            if s.get("executive_summary"):
                parts.append(s["executive_summary"])
            for k in ("drug_name", "indication", "company"):
                if s.get(k):
                    parts.append(s[k])
        elif isinstance(s, str):
            parts.append(s)
    if article.get("snippet"):
        parts.append(article["snippet"])
    meta = article.get("meta") or {}
    for k in ("sponsor", "conditions", "generic_names", "brand_names", "therapeutic_area", "inn"):
        v = meta.get(k)
        if v:
            parts.append(str(v) if isinstance(v, str) else " ".join(str(x) for x in (v or [])))
    return " ".join(parts).lower()


def _get_competitor_mentions(text: str) -> list[dict]:
    found = []
    for canonical, aliases in _COMPETITOR_MAP.items():
        check = {canonical.lower()} | {a.lower() for a in aliases}
        for term in check:
            if len(term) >= 4 and term in text:
                found.append({"competitor": canonical, "aliases": list(aliases), "matched": term})
                break
    return found


def _get_affected_assets(text: str, pipeline: dict) -> list[dict]:
    assets = pipeline.get("assets", [])
    affected, seen_ids = [], set()

    def asset_ref(a):
        return {"id": a.get("id"), "drug_name": a.get("drug_name"), "drug_code": a.get("drug_code"),
                "mechanism": a.get("mechanism"), "phase": a.get("phase"),
                "indications": a.get("indications", []), "therapeutic_area": a.get("therapeutic_area")}

    for a in assets:
        for field in ("drug_name", "drug_code"):
            val = a.get(field)
            if val and val.lower() in text:
                aid = a.get("id")
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    affected.append({"asset": asset_ref(a), "impact_type": "direct_mention",
                                     "reason": f"Pipeline asset '{val}' mentioned", "severity": "high"})
        for ind in a.get("indications", []):
            if ind and len(ind) >= 5 and ind.lower() in text:
                aid = a.get("id")
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    affected.append({"asset": asset_ref(a), "impact_type": "indication_overlap",
                                     "reason": f"Indication '{ind}' mentioned", "severity": "medium"})
    for kw, asset_ids in _MECHANISM_TO_ASSETS.items():
        if kw in text:
            for aid in asset_ids:
                if aid not in seen_ids:
                    a = next((x for x in assets if x.get("id") == aid), None)
                    if a:
                        seen_ids.add(aid)
                        affected.append({"asset": asset_ref(a), "impact_type": "mechanism_overlap",
                                         "reason": f"Mechanism keyword '{kw}' matches", "severity": "medium"})
    return affected


def _generate_recommendations(affected: list, competitors: list, articles_count: int) -> list[dict]:
    recs = []
    if affected:
        recs.append({"type": "monitor", "priority": "high", "title": "Monitor affected pipeline assets",
                     "description": f"{len(affected)} pipeline asset(s) referenced. Review competitive landscape.",
                     "actions": ["Track competitor trial progress", "Monitor regulatory filings", "Update briefings"]})
    if competitors:
        recs.append({"type": "competitive", "priority": "high", "title": "Competitor activity detected",
                     "description": f"Competitors mentioned: {', '.join(set(c['competitor'] for c in competitors))}.",
                     "actions": ["Compare competitor phase", "Assess differentiation", "Consider positioning"]})
    if not affected and not competitors:
        recs.append({"type": "informational", "priority": "low", "title": "No direct pipeline overlap",
                     "description": "No direct overlap. Try broader keywords.", "actions": ["Try CKD, obesity, NSCLC"]})
    return recs


def analyze_pipeline_impact(articles: list[dict], news_articles: list[dict] | None = None,
                           pipeline_data: dict | None = None) -> dict:
    pipeline = pipeline_data or CLINICAL_PIPELINE_JSON
    all_articles = list(articles) + (news_articles or [])
    if not all_articles:
        return {"pipeline": {"company": pipeline.get("company"), "as_of": pipeline.get("as_of")},
                "affected_assets": [], "competitor_mentions": [], "articles_analyzed": 0,
                "recommendations": _generate_recommendations([], [], 0), "summary": "No articles to analyze."}
    all_affected, all_competitors, article_impacts = [], [], []
    for i, art in enumerate(all_articles):
        text = _extract_text(art)
        affected = _get_affected_assets(text, pipeline)
        competitors = _get_competitor_mentions(text)
        for a in affected:
            if not any(x["asset"]["id"] == a["asset"]["id"] and x["impact_type"] == a["impact_type"] for x in all_affected):
                all_affected.append(a)
        for c in competitors:
            if c not in all_competitors:
                all_competitors.append(c)
        if affected or competitors:
            article_impacts.append({"index": i, "title": art.get("title", ""), "source": art.get("source", ""),
                                   "affected_count": len(affected), "competitor_count": len(competitors)})
    severity_order = {"high": 0, "medium": 1, "low": 2}
    seen = {}
    for a in all_affected:
        aid = a["asset"]["id"]
        prev = seen.get(aid)
        if not prev or severity_order.get(a["severity"], 99) < severity_order.get(prev["severity"], 99):
            seen[aid] = a
    all_affected = list(seen.values())
    recommendations = _generate_recommendations(all_affected, all_competitors, len(all_articles))
    summary_parts = []
    if all_affected:
        summary_parts.append(f"{len(all_affected)} pipeline asset(s) affected.")
    if all_competitors:
        summary_parts.append(f"{len(all_competitors)} competitor(s) mentioned.")
    summary = " ".join(summary_parts) if summary_parts else "No significant overlap detected."
    return {"pipeline": {"company": pipeline.get("company"), "as_of": pipeline.get("as_of"),
                         "total_assets": len(pipeline.get("assets", []))},
            "affected_assets": all_affected, "competitor_mentions": all_competitors,
            "articles_analyzed": len(all_articles), "articles_with_signals": len(article_impacts),
            "article_impacts": article_impacts[:20], "recommendations": recommendations, "summary": summary}


# ── Demo Data ───────────────────────────────────────────────────────────
_DEMO_CLUSTERS = {
    0: [
        {"title": "Novo Nordisk Wins FDA Nod for Ozempic in CKD", "link": "https://example.com/novo-fda",
         "source": "Reuters", "published_date": "Feb 20, 2026", "keyword": "CKD drug pipeline",
         "summary": {"bullet_points": [
             "Semaglutide received FDA approval for CKD in type 2 diabetes patients.",
             "Phase 3 FLOW trial showed 24% reduction in kidney disease progression.",
             "Drug is already approved for T2D and obesity indications.",
             "EMA filing planned for Q2 2025 for the new renal indication.",
             "CKD indication projected to add $3B in annual revenue.",
         ], "executive_summary": (
             "Novo Nordisk secured FDA approval for semaglutide in chronic kidney disease "
             "associated with type 2 diabetes. The FLOW trial demonstrated significant renal "
             "protective benefits versus placebo. This positions semaglutide as a leading "
             "multi-indication asset in cardiorenal medicine."
         ), "drug_name": "semaglutide (Ozempic)", "company": "Novo Nordisk",
         "indication": "CKD in type 2 diabetes", "regulatory_status": "FDA approved; EMA filing Q2 2025"}},
        {"title": "Eli Lilly Launches Phase 3 Renal Trial for Mounjaro", "link": "https://example.com/lilly-renal",
         "source": "FiercePharma", "published_date": "Feb 19, 2026", "keyword": "CKD drug pipeline",
         "summary": {"bullet_points": [
             "Tirzepatide Phase 3 renal outcomes trial initiated by Eli Lilly.",
             "Trial targets 3,500 patients with CKD and T2D.",
             "Primary endpoint is sustained eGFR decline over 3 years.",
             "Results expected H2 2026.",
             "Analysts see this as a direct competitive response to Ozempic FLOW data.",
         ], "executive_summary": (
             "Eli Lilly launched a Phase 3 trial evaluating tirzepatide for renal outcomes "
             "in CKD patients with type 2 diabetes. The study aims to replicate the success "
             "of Novo Nordisk's FLOW trial. Competitive dynamics in the GLP-1/CKD space are intensifying."
         ), "drug_name": "tirzepatide (Mounjaro)", "company": "Eli Lilly",
         "indication": "CKD in type 2 diabetes", "regulatory_status": "Phase 3 initiated"}},
    ],
    1: [
        {"title": "Bayer Finerenone 4-Year Data Reinforces CKD Benefits", "link": "https://example.com/bayer-finerenone",
         "source": "Endpoints News", "published_date": "Feb 18, 2026", "keyword": "CKD treatment",
         "summary": {"bullet_points": [
             "Bayer's finerenone showed long-term renal benefits in 4-year data.",
             "FIDELITY pooled analysis confirms sustained eGFR preservation.",
             "Drug approved in US, EU, and Japan for CKD in T2D.",
             "Real-world evidence supports clinical trial findings.",
             "Bayer exploring combination therapy with SGLT2 inhibitors.",
         ], "executive_summary": (
             "Bayer presented 4-year pooled data confirming finerenone's sustained renal and "
             "cardiovascular benefits in CKD patients. The FIDELITY analysis reinforces its "
             "position as a cornerstone MRA therapy. Bayer is now investigating synergistic "
             "combinations with SGLT2 inhibitors."
         ), "drug_name": "finerenone (Kerendia)", "company": "Bayer",
         "indication": "CKD in type 2 diabetes", "regulatory_status": "Approved (US, EU, Japan)"}},
        {"title": "AstraZeneca's Dapagliflozin Gains New CKD Label Extension", "link": "https://example.com/az-dapa",
         "source": "BioPharma Dive", "published_date": "Feb 17, 2026", "keyword": "CKD treatment",
         "summary": {"bullet_points": [
             "Dapagliflozin label extended to cover broader CKD population.",
             "DAPA-CKD long-term follow-up confirms durability of kidney protection.",
             "SGLT2 inhibitors now considered standard of care in CKD guidelines.",
             "AstraZeneca projects $1.5B in incremental CKD-related revenue.",
             "Combination studies with finerenone and GLP-1 agonists underway.",
         ], "executive_summary": (
             "AstraZeneca received a label extension for dapagliflozin covering a broader CKD "
             "population. Long-term DAPA-CKD data continues to demonstrate kidney-protective "
             "effects. SGLT2 inhibitors are now recommended as first-line therapy in major CKD guidelines."
         ), "drug_name": "dapagliflozin (Farxiga)", "company": "AstraZeneca",
         "indication": "Chronic kidney disease (broad)", "regulatory_status": "Label extension approved"}},
    ],
    -1: [
        {"title": "Global CKD Prevalence Rising Sharply in Asia-Pacific Region", "link": "https://example.com/ckd-apac",
         "source": "The Lancet", "published_date": "Feb 17, 2026", "keyword": "CKD epidemiology", "summary": None},
        {"title": "WHO Calls for Universal Screening of Kidney Disease", "link": "https://example.com/who-screening",
         "source": "BMJ", "published_date": "Feb 15, 2026", "keyword": "CKD screening", "summary": None},
    ],
}


def _run_pipeline(keywords: list[str]) -> list[dict]:
    raw = fetch_all_sources(keywords, max_per_source=50)
    if not raw:
        return []
    def parse_date(d):
        return "0000-00-00" if not d or d in ("Unknown", "See EMA EPAR", "See FDA label") else d
    by_source = defaultdict(list)
    for item in raw:
        by_source[item["source"]].append(item)
    selected = []
    for source, items in by_source.items():
        items.sort(key=lambda x: parse_date(x.get("published_date", "")), reverse=True)
        selected.extend(items[:10])
    selected.sort(key=lambda x: parse_date(x.get("published_date", "")), reverse=True)
    return [{"title": r["title"], "link": r["link"], "source": r["source"], "published_date": r["published_date"],
             "keyword": r.get("keyword", ""), "full_text": r.get("full_text", ""), "meta": r.get("meta", {})}
             for r in selected]


# ── Flask App ──────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    return Response(DASHBOARD_HTML, mimetype="text/html")


@app.route("/api/demo")
def api_demo():
    return jsonify({str(k): v for k, v in _DEMO_CLUSTERS.items()})


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    raw = data.get("keywords", "")
    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not keywords:
        return jsonify({"error": "No keywords provided."}), 400
    try:
        articles = _run_pipeline(keywords)
    except Exception as exc:
        logger.exception("Pipeline error")
        return jsonify({"error": f"Pipeline error: {exc}"}), 500
    return jsonify({"articles": articles, "count": len(articles)})


@app.route("/api/pipeline-impact", methods=["POST"])
def api_pipeline_impact():
    data = request.get_json(silent=True) or {}
    articles = data.get("articles", [])
    news_articles = data.get("news_articles", [])
    if not articles and not news_articles:
        return jsonify({"error": "No articles provided. Run a search first."}), 400
    try:
        result = analyze_pipeline_impact(articles=articles, news_articles=news_articles,
                                         pipeline_data=CLINICAL_PIPELINE_JSON)
        return jsonify(result)
    except Exception as exc:
        logger.exception("Pipeline impact analysis error")
        return jsonify({"error": f"Analysis error: {exc}"}), 500


@app.route("/api/biohealth-news")
def api_biohealth_news():
    try:
        count = request.args.get("count", 10, type=int)
        count = min(max(count, 1), 30)
        raw_keywords = request.args.get("keywords", "").strip()
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        if keywords:
            articles, overall_summary = fetch_biohealth_news_by_keywords(keywords, max_results=count, enrich_with_content=True)
            fallback = len(articles) == 0
        else:
            articles = fetch_top_biohealth_news(total=count)
            overall_summary = ""
            fallback = None
        return jsonify({"articles": articles, "count": len(articles),
                        "sources": list(set(a["source"] for a in articles)),
                        "keywords": keywords, "overall_summary": overall_summary if keywords else None,
                        "fallback_to_unfiltered": fallback if keywords else None})
    except Exception as exc:
        logger.exception("Biohealth news error")
        return jsonify({"error": f"Failed to fetch news: {exc}"}), 500


# ── Embedded Dashboard HTML ─────────────────────────────────────────────
DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ShMo Pharma Intelligence</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f1f4f9;--surface:#fff;--surface-alt:#f7f9fc;--primary:#1a3c6e;--primary-light:#e8eef7;
--accent:#2e7d32;--accent-light:#e8f5e9;--accent-text:#1b5e20;--warn:#e65100;--warn-light:#fff3e0;
--text:#1e293b;--text-secondary:#64748b;--border:#e2e8f0;--radius:10px;--radius-sm:6px;
--shadow:0 1px 3px rgba(0,0,0,.06);--shadow-md:0 4px 12px rgba(0,0,0,.07);--transition:all .2s ease}
html{font-size:15px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,sans-serif;
background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh}
.app-header{background:linear-gradient(135deg,var(--primary),#2b5ea7);color:#fff;padding:0 2rem;
position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.12)}
.header-inner{max-width:1120px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:60px}
.header-inner h1{font-size:1.15rem;font-weight:700}
.container{max-width:1120px;margin:0 auto;padding:1.5rem 2rem 3rem}
.search-panel{background:var(--surface);border-radius:var(--radius);box-shadow:var(--shadow);
padding:1.25rem 1.5rem;display:flex;gap:.75rem;align-items:center;flex-wrap:wrap;margin-bottom:1.5rem}
.search-panel input{flex:1;min-width:220px;padding:.55rem .85rem;border:1.5px solid var(--border);
border-radius:var(--radius-sm);font-size:.9rem;outline:none;transition:var(--transition)}
.search-panel input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-light)}
.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.55rem 1.1rem;border-radius:var(--radius-sm);
font-size:.85rem;font-weight:600;cursor:pointer;border:none;transition:var(--transition)}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:#244d85}
.btn-outline{background:transparent;color:var(--primary);border:1.5px solid var(--border)}
.btn-outline:hover{background:var(--primary-light)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.stats-strip{display:flex;gap:1rem;margin-bottom:1.5rem;flex-wrap:wrap}
.stat-card{flex:1;min-width:140px;background:var(--surface);border-radius:var(--radius);
box-shadow:var(--shadow);padding:1rem 1.25rem;text-align:center}
.stat-card .value{font-size:1.7rem;font-weight:700;color:var(--primary)}
.stat-card .label{font-size:.75rem;color:var(--text-secondary);text-transform:uppercase}
.pipeline{display:flex;gap:0;margin-bottom:1.5rem;background:var(--surface);border-radius:var(--radius);
box-shadow:var(--shadow);overflow:hidden}
.pipeline .step{flex:1;padding:.65rem .5rem;text-align:center;font-size:.75rem;font-weight:600;
color:var(--text-secondary);border-right:1px solid var(--border)}
.pipeline .step:last-child{border-right:none}
.pipeline .step.active{color:var(--primary);background:var(--primary-light)}
.pipeline .step.done{color:#fff;background:var(--accent)}
.cluster-section{margin-bottom:1.75rem}
.cluster-header{display:flex;align-items:center;gap:.6rem;margin-bottom:.75rem}
.cluster-badge{display:inline-block;font-size:.7rem;font-weight:700;padding:.2rem .6rem;
border-radius:4px;text-transform:uppercase}
.cluster-badge.topic{background:var(--accent-light);color:var(--accent-text)}
.cluster-badge.noise{background:var(--warn-light);color:var(--warn)}
.article-card{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);
box-shadow:var(--shadow);margin-bottom:.75rem;overflow:hidden;transition:var(--transition)}
.article-card:hover{box-shadow:var(--shadow-md)}
.card-main{padding:1.1rem 1.25rem;cursor:pointer;display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem}
.card-main .title{font-size:.95rem;font-weight:600;color:var(--primary);line-height:1.35;text-decoration:none}
.card-main .title:hover{text-decoration:underline}
.card-main .meta{font-size:.75rem;color:var(--text-secondary);margin-top:.3rem}
.card-main .chevron{font-size:.85rem;color:var(--text-secondary);transition:transform .2s}
.article-card.open .chevron{transform:rotate(180deg)}
.card-detail{display:none;padding:0 1.25rem 1.1rem;border-top:1px solid var(--border)}
.article-card.open .card-detail{display:block;padding-top:1rem}
.intel-tags{display:flex;flex-wrap:wrap;gap:.35rem;margin-bottom:.75rem}
.intel-tag{display:inline-flex;align-items:center;gap:.25rem;background:var(--accent-light);
color:var(--accent-text);font-size:.72rem;padding:.2rem .55rem;border-radius:3px}
.exec-summary{font-size:.85rem;line-height:1.55;padding:.75rem 1rem;background:var(--surface-alt);
border-left:3px solid var(--primary);border-radius:0 var(--radius-sm) var(--radius-sm) 0}
.bullet-list{list-style:none;padding:0;margin:0}
.bullet-list li{font-size:.83rem;line-height:1.5;padding:.3rem 0 .3rem 1.2rem;position:relative}
.bullet-list li::before{content:'';position:absolute;left:0;top:.65rem;width:6px;height:6px;
border-radius:50%;background:var(--accent)}
.read-link{display:inline-flex;align-items:center;gap:.3rem;font-size:.78rem;font-weight:600;
color:var(--primary);text-decoration:none;margin-top:.5rem}
.state-message{text-align:center;padding:3rem 1rem;color:var(--text-secondary)}
.state-message .icon{font-size:2.5rem;margin-bottom:.75rem;display:block}
.state-message h3{font-size:1rem;color:var(--text);margin-bottom:.35rem}
.spinner{display:inline-block;width:20px;height:20px;border:2.5px solid rgba(255,255,255,.3);
border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.app-footer{text-align:center;padding:1.5rem;font-size:.75rem;color:var(--text-secondary)}
.impact-section{margin-top:2rem;padding-top:1.5rem;border-top:2px solid var(--border)}
.impact-card{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);
box-shadow:var(--shadow);padding:1.25rem 1.5rem;margin-bottom:1rem}
.impact-card h4{font-size:.95rem;color:var(--primary);margin:0 0 .75rem}
.impact-badge{font-size:.7rem;padding:.2rem .5rem;border-radius:4px;font-weight:600;text-transform:uppercase}
.impact-badge.high{background:#ffebee;color:#c62828}
.impact-badge.medium{background:#fff3e0;color:#e65100}
.impact-badge.low{background:#e8f5e9;color:#2e7d32}
.impact-list{list-style:none;padding:0;margin:0}
.impact-list li{padding:.5rem 0;border-bottom:1px solid var(--border);font-size:.85rem}
.news-section{margin-top:2rem;padding-top:1.5rem;border-top:2px solid var(--border)}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;flex-wrap:wrap}
.section-header h2{font-size:1.15rem;font-weight:700;color:var(--primary)}
.btn-sm{padding:.4rem .8rem;font-size:.78rem}
.news-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}
.news-card{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);
box-shadow:var(--shadow);padding:1rem 1.25rem}
.news-card .news-source{font-size:.7rem;font-weight:600;text-transform:uppercase;margin-bottom:.4rem}
.news-card .news-title{font-size:.9rem;font-weight:600;color:var(--primary);line-height:1.4}
.news-card .news-title a{color:inherit;text-decoration:none}
.news-card .news-date{font-size:.72rem;color:var(--text-secondary)}
.news-card .news-snippet{font-size:.8rem;color:var(--text);line-height:1.5}
</style>
</head>
<body>
<header class="app-header">
  <div class="header-inner">
    <h1>ShMo Pharma Intelligence <span style="opacity:.7;font-weight:400;margin-left:.5rem">Competitive Monitoring Dashboard</span></h1>
  </div>
</header>
<div class="container">
  <div class="search-panel">
    <input id="kw-input" type="text" placeholder="Drug or disease name (e.g. semaglutide, chronic kidney disease, tirzepatide)">
    <button class="btn btn-primary" id="btn-search" onclick="runSearch()"><span id="search-label">Search</span></button>
    <button class="btn btn-outline" onclick="loadDemo()">Load Demo</button>
  </div>
  <div class="pipeline" id="pipeline">
    <div class="step" data-step="ctgov"><span class="icon">1</span>ClinicalTrials.gov</div>
    <div class="step" data-step="fda"><span class="icon">2</span>FDA Label</div>
    <div class="step" data-step="ema"><span class="icon">3</span>EMA</div>
    <div class="step" data-step="sort"><span class="icon">4</span>Sort &amp; Select Top 15</div>
  </div>
  <div class="stats-strip" id="stats" style="display:none">
    <div class="stat-card"><div class="value" id="st-articles">0</div><div class="label">Results</div></div>
    <div class="stat-card"><div class="value" id="st-clusters">0</div><div class="label">Sources</div></div>
    <div class="stat-card"><div class="value" id="st-drugs">0</div><div class="label">Clinical Trials</div></div>
    <div class="stat-card"><div class="value" id="st-companies">0</div><div class="label">FDA Labels</div></div>
  </div>
  <div id="results">
    <div class="state-message" id="empty-state">
      <span class="icon">&#128269;</span>
      <h3>No results yet</h3>
      <p>Enter a drug or disease name and click <strong>Search</strong> to query ClinicalTrials.gov, FDA, and EMA.<br>Or click <strong>Load Demo</strong> to see sample data.</p>
    </div>
  </div>
  <div class="impact-section" id="impact-section">
    <div class="section-header">
      <h2>📊 Pipeline Impact Analysis</h2>
      <button class="btn btn-primary btn-sm" id="btn-analyze" onclick="runPipelineImpact()"><span id="analyze-label">Analyze Impact</span></button>
    </div>
    <div id="impact-container">
      <div class="state-message">
        <span class="icon">📋</span>
        <h3>Ready to analyze</h3>
        <p>Run a search or load demo data, then click <strong>Analyze Impact</strong>.</p>
      </div>
    </div>
  </div>
  <div class="news-section" id="biohealth-section">
    <div class="section-header">
      <h2>📰 Biohealth News</h2>
      <button class="btn btn-outline btn-sm" onclick="loadBiohealthNews()"><span id="news-btn-label">Refresh</span></button>
    </div>
    <div id="news-container">
      <div class="state-message">
        <span class="icon">📰</span>
        <h3>Loading news...</h3>
        <p>Fetching latest biohealth articles</p>
      </div>
    </div>
  </div>
</div>
<footer class="app-footer">ShMo Competitor Agent &middot; Pharma Competitive Intelligence Platform</footer>
<script>
let currentData = null;
let lastSearchKeyword = '';
let currentNewsArticles = [];
const STEPS = ['ctgov','fda','ema','sort'];
function setPipeline(activeIdx){
  document.querySelectorAll('.pipeline .step').forEach((el,i)=>{
    el.classList.remove('active','done');
    if(i<activeIdx)el.classList.add('done');
    else if(i===activeIdx)el.classList.add('active');
  });
}
function clearPipeline(){document.querySelectorAll('.pipeline .step').forEach(el=>{el.classList.remove('active','done');});}
function completePipeline(){document.querySelectorAll('.pipeline .step').forEach(el=>{el.classList.remove('active');el.classList.add('done');});}
async function loadDemo(){
  setPipeline(0);document.getElementById('btn-search').disabled=true;document.getElementById('search-label').innerHTML='<span class="spinner"></span> Running';
  let step=0;const iv=setInterval(()=>{step++;if(step<4)setPipeline(step);},300);
  try{
    const res=await fetch('/api/demo');const data=await res.json();
    clearInterval(iv);completePipeline();renderClusters(data);showImpactSection();
  }catch(e){clearInterval(iv);clearPipeline();showError('Failed to load demo data.');}
  finally{document.getElementById('btn-search').disabled=false;document.getElementById('search-label').textContent='Search';}
}
async function runSearch(){
  const kw=document.getElementById('kw-input').value.trim();
  if(!kw)return;
  setPipeline(0);document.getElementById('btn-search').disabled=true;document.getElementById('search-label').innerHTML='<span class="spinner"></span> Running';
  let step=0;const iv=setInterval(()=>{step++;if(step<4)setPipeline(step);},2000);
  try{
    const res=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keywords:kw})});
    const data=await res.json();clearInterval(iv);
    if(data.error){clearPipeline();showError(data.error);return;}
    completePipeline();lastSearchKeyword=kw;renderArticles(data);showImpactSection();loadBiohealthNews(kw);
  }catch(e){clearInterval(iv);clearPipeline();showError('Network error.');}
  finally{document.getElementById('btn-search').disabled=false;document.getElementById('search-label').textContent='Search';}
}
function renderArticles(data){
  currentData=data;const container=document.getElementById('results');const articles=data.articles||[];
  const sources={};articles.forEach(a=>{sources[a.source]=(sources[a.source]||0)+1;});
  document.getElementById('stats').style.display='flex';
  document.getElementById('st-articles').textContent=articles.length;
  document.getElementById('st-clusters').textContent=Object.keys(sources).length;
  document.getElementById('st-drugs').textContent=sources['ClinicalTrials.gov']||0;
  document.getElementById('st-companies').textContent=sources['FDA Label']||0;
  if(articles.length===0){container.innerHTML='<div class="state-message"><span class="icon">&#128269;</span><h3>No results found</h3><p>Try a different search term.</p></div>';return;}
  container.innerHTML=`<div class="cluster-section"><div class="cluster-header"><span class="cluster-badge topic">Latest ${articles.length} Results</span></div>${articles.map((a,i)=>renderArticle(a,i)).join('')}</div>`;
}
function renderClusters(data){
  currentData=data;const container=document.getElementById('results');
  const sortedKeys=Object.keys(data).map(Number).sort((a,b)=>{if(a===-1)return 1;if(b===-1)return -1;return a-b;});
  let total=0;sortedKeys.forEach(k=>{total+=data[String(k)].length;});
  document.getElementById('stats').style.display='flex';
  document.getElementById('st-articles').textContent=total;
  document.getElementById('st-clusters').textContent=sortedKeys.filter(k=>k!==-1).length;
  document.getElementById('st-drugs').textContent='-';document.getElementById('st-companies').textContent='-';
  let html='';let clusterNum=0;
  sortedKeys.forEach(k=>{
    const articles=data[String(k)];const isNoise=k===-1;if(!isNoise)clusterNum++;
    html+=`<div class="cluster-section"><div class="cluster-header"><span class="cluster-badge ${isNoise?'noise':'topic'}">${isNoise?'Unclustered':`Topic Cluster ${clusterNum}`}</span><span class="cluster-count">${articles.length} article(s)</span></div>${articles.map((a,i)=>renderArticle(a,`${k}-${i}`)).join('')}</div>`;
  });
  container.innerHTML=html;
}
function renderArticle(a,uid){
  const fullText=a.full_text||'';const meta=a.meta||{};
  let intelHtml='';const tags=[];
  if(meta.phase)tags.push(['Phase',meta.phase]);if(meta.status)tags.push(['Status',meta.status]);
  if(meta.sponsor)tags.push(['Sponsor',meta.sponsor]);if(meta.nct_id)tags.push(['NCT ID',meta.nct_id]);
  if(meta.brand_names&&meta.brand_names.length)tags.push(['Brand',meta.brand_names.slice(0,2).join(', ')]);
  if(meta.generic_names&&meta.generic_names.length)tags.push(['Generic',meta.generic_names[0]]);
  if(meta.therapeutic_area)tags.push(['Indication',meta.therapeutic_area.split(';')[0]]);
  if(tags.length)intelHtml=`<div class="intel-tags">${tags.map(([l,v])=>`<span class="intel-tag"><strong>${esc(l)}:</strong> ${esc(v)}</span>`).join('')}</div>`;
  let summaryHtml='';
  if(fullText){const lines=fullText.split('\\n').filter(l=>l.trim());summaryHtml=`<div class="exec-summary" style="white-space:pre-line">${esc(lines.slice(0,10).join('\\n'))}</div>`;}
  const s=a.summary;let oldSummaryHtml='';
  if(s&&s.executive_summary){oldSummaryHtml=`<div class="exec-summary">${esc(s.executive_summary)}</div>`;if(s.bullet_points&&s.bullet_points.length)oldSummaryHtml+=`<ul class="bullet-list">${s.bullet_points.map(bp=>`<li>${esc(bp)}</li>`).join('')}</ul>`;}
  const hasDetail=intelHtml||summaryHtml||oldSummaryHtml;
  return `<div class="article-card" id="card-${uid}"><div class="card-main" onclick="${hasDetail?`toggleCard('${uid}')`:''}"><div><span class="title" style="cursor:pointer">${esc(a.title)}</span><div class="meta">${esc(a.source)} &middot; ${esc(a.published_date)}</div></div>${hasDetail?'<span class="chevron">&#9660;</span>':''}</div>${hasDetail?`<div class="card-detail">${intelHtml}${summaryHtml||oldSummaryHtml}<a class="read-link" href="${esc(a.link)}" target="_blank">View original source &rarr;</a></div>`:''}</div>`;
}
function toggleCard(uid){document.getElementById('card-'+uid).classList.toggle('open');}
function showError(msg){document.getElementById('results').innerHTML=`<div class="state-message"><span class="icon">&#9888;</span><h3>Error</h3><p>${esc(msg)}</p></div>`;document.getElementById('stats').style.display='none';}
function esc(s){if(s==null)return'';const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
document.getElementById('kw-input').addEventListener('keydown',e=>{if(e.key==='Enter')runSearch();});
async function loadBiohealthNews(keyword){
  const container=document.getElementById('news-container');const btnLabel=document.getElementById('news-btn-label');
  const kw=(keyword!==undefined&&keyword!==null)?String(keyword).trim():lastSearchKeyword;
  btnLabel.innerHTML='<span class="spinner" style="border-color:var(--primary);border-top-color:transparent;width:14px;height:14px"></span>';
  try{
    let url='/api/biohealth-news?count='+(kw?15:10);if(kw)url+='&keywords='+encodeURIComponent(kw);
    const res=await fetch(url);const data=await res.json();
    if(data.error){container.innerHTML=`<div class="state-message"><span class="icon">⚠️</span><h3>Error</h3><p>${esc(data.error)}</p></div>`;return;}
    const articles=data.articles||[];currentNewsArticles=articles;
    if(articles.length===0){container.innerHTML=`<div class="state-message"><span class="icon">📭</span><h3>No news available</h3><p>Try again later.</p></div>`;return;}
    container.innerHTML=`<div class="news-grid">${articles.map(renderNewsCard).join('')}</div>`;
  }catch(e){container.innerHTML=`<div class="state-message"><span class="icon">⚠️</span><h3>Network Error</h3></div>`;}
  finally{btnLabel.textContent='Refresh';}
}
function renderNewsCard(article){const snippet=article.summary||article.snippet||'';return `<div class="news-card"><div class="news-source">${esc(article.source)}</div><div class="news-title"><a href="${esc(article.link)}" target="_blank">${esc(article.title)}</a></div><div class="news-date">${esc(article.published_date)}</div>${snippet?`<div class="news-snippet">${esc(snippet)}</div>`:''}</div>`;}
document.addEventListener('DOMContentLoaded',()=>{loadBiohealthNews();});
function showImpactSection(){document.getElementById('impact-section').style.display='block';document.getElementById('impact-container').innerHTML=`<div class="state-message"><span class="icon">📋</span><h3>Ready to analyze</h3><p>Click <strong>Analyze Impact</strong>.</p></div>`;}
function getArticlesForImpact(){const articles=[];if(!currentData)return articles;if(Array.isArray(currentData.articles))return currentData.articles;if(typeof currentData==='object'){for(const k of Object.keys(currentData)){const arr=currentData[k];if(Array.isArray(arr))articles.push(...arr);}}return articles;}
async function runPipelineImpact(){
  const articles=getArticlesForImpact();const news=currentNewsArticles||[];
  if(!articles.length&&!news.length){alert('No articles to analyze. Run a search or load demo first.');return;}
  const btn=document.getElementById('btn-analyze');const label=document.getElementById('analyze-label');
  btn.disabled=true;label.innerHTML='<span class="spinner" style="border-color:var(--primary);border-top-color:transparent;width:14px;height:14px"></span>';
  try{
    const res=await fetch('/api/pipeline-impact',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({articles,news_articles:news})});
    const data=await res.json();
    if(data.error){document.getElementById('impact-container').innerHTML=`<div class="state-message"><span class="icon">⚠️</span><h3>Error</h3><p>${esc(data.error)}</p></div>`;return;}
    renderImpactResults(data);
  }catch(e){document.getElementById('impact-container').innerHTML=`<div class="state-message"><span class="icon">⚠️</span><h3>Network Error</h3></div>`;}
  finally{btn.disabled=false;label.textContent='Analyze Impact';}
}
function renderImpactResults(data){
  const pipeline=data.pipeline||{};const affected=data.affected_assets||[];const competitors=data.competitor_mentions||[];const recs=data.recommendations||[];const summary=data.summary||'';
  let html=`<div class="impact-card"><h4>Summary</h4><p style="margin:0">${esc(summary)}</p><p style="margin:.5rem 0 0;font-size:.78rem;color:var(--text-secondary)">Pipeline: ${esc(pipeline.company)} &middot; ${data.articles_analyzed||0} articles analyzed</p></div>`;
  if(affected.length)html+=`<div class="impact-card"><h4>Affected Pipeline Assets <span class="impact-badge high">${affected.length}</span></h4><ul class="impact-list">${affected.map(a=>`<li><span class="impact-badge ${a.severity||'medium'}">${esc(a.severity||'')}</span><div><strong>${esc(a.asset.drug_name||a.asset.drug_code||a.asset.id)}</strong><br><span style="font-size:.8rem;color:var(--text-secondary)">${esc(a.reason)}</span></div></li>`).join('')}</ul></div>`;
  if(competitors.length){const unique=[...new Set(competitors.map(c=>c.competitor))];html+=`<div class="impact-card"><h4>Competitor Mentions</h4><p style="margin:0">${esc(unique.join(', '))}</p></div>`;}
  if(recs.length)html+=`<div class="impact-card"><h4>Recommendations</h4>${recs.map(r=>`<div style="margin-bottom:1rem"><strong>${esc(r.title)}</strong> <span class="impact-badge ${r.priority||'medium'}">${esc(r.priority||'')}</span><p style="margin:.35rem 0 .5rem;font-size:.85rem">${esc(r.description)}</p>${r.actions&&r.actions.length?`<ul style="padding-left:1.25rem;margin:.5rem 0 0">${r.actions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}</div>`).join('')}</div>`;
  document.getElementById('impact-container').innerHTML=html;
}
</script>
</body>
</html>'''


if __name__ == "__main__":
    app.run(debug=True, port=5001)
