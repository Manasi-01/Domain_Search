# This script uses the serper api and the gemini llm

import streamlit as st
import requests
import tldextract
import time
import os
from dotenv import load_dotenv
from collections import Counter
# Gemini LLM imports
import google.generativeai as genai

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

# Search Google/Serper for a query and return links
def search_google(query, num=40):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query, "num": num}
    res = requests.post(url, headers=headers, json=payload)
    if res.ok:
        return [r["link"] for r in res.json().get("organic", [])]
    return []

# Extract root domains from links
def extract_root_domains(links):
    roots = []
    for link in links:
        ext = tldextract.extract(link)
        if ext.domain and ext.suffix:
            roots.append(ext.domain.lower())
    return roots

# Extract all www.<root>.* domains and return full URLs
def get_all_domains(root):
    found_domains = set()
    excluded_tlds = set(["com"])
    found_domains.add(f"https://www.{root}.com")
    while True:
        query = f"site:www.{root}.*" + (" " + " ".join(f"-{tld}" for tld in sorted(excluded_tlds)) if excluded_tlds else "")
        links = search_google(query, num=40)
        if not links:
            break
        for link in links:
            ext = tldextract.extract(link)
            if ext.domain.lower() == root and ext.suffix:
                url = f"https://www.{ext.domain.lower()}.{ext.suffix.lower()}"
                found_domains.add(url)
                excluded_tlds.add(ext.suffix.lower())
        time.sleep(1)
    return sorted(found_domains)


# Batch filter function using Gemini for social media and news domains only
@st.cache_data(show_spinner=False)
def filter_social_and_news_domains_llm(domains):
    if not gemini_model or not domains:
        return domains  # If Gemini not configured, don't filter
    prompt = (
    "Given the following list of domain names, return ONLY the ones that are "
    "social media websites, news websites, online encyclopedias (like Wikipedia), "
    "search engines (like Google), or any general public knowledge directories. "
    "Reply with a comma-separated list of the root domains only, no explanation.\n\n"
    f"Domains: {', '.join([d + '.com' for d in domains])}"
    )
    try:
        response = gemini_model.generate_content(prompt)
        answer = response.text.strip().lower()
        print(f"Gemini batch response: {answer}")
        flagged_domains = [d.strip().replace('.com', '') for d in answer.split(',') if d.strip()]
        return [d for d in domains if d not in flagged_domains]
    except Exception as e:
        print(f"Gemini batch error: {e}")
        return domains

def main():
    st.title("Company Domain Finder")
    st.write("Enter a company name to find all its domains using Google.")
    company = st.text_input("Enter the company name:")
    if 'root_options' not in st.session_state:
        st.session_state['root_options'] = []
    if 'expanded_domains' not in st.session_state:
        st.session_state['expanded_domains'] = {}  # {root: [domains]}
    if 'deleted_roots' not in st.session_state:
        st.session_state['deleted_roots'] = set()
    if 'deleted_domains' not in st.session_state:
        st.session_state['deleted_domains'] = {}  # {root: set(domains)}

    if st.button("Search for Root Domains"):
        if not company:
            st.warning("Please enter a company name.")
        else:
            with st.spinner("Searching for likely root domains..."):
                links = search_google(company, num=40)
                roots = extract_root_domains(links)
                if not roots:
                    st.warning("No root domains found in search results.")
                else:
                    root_counts = Counter(roots)
                    most_common = [r for r, _ in root_counts.most_common()]
                    with st.spinner("Filtering out social media and news domains"):
                        filtered_roots = filter_social_and_news_domains_llm(most_common)
                    st.session_state['root_options'] = filtered_roots
                    st.session_state['expanded_domains'] = {}
                    st.session_state['deleted_roots'] = set()
                    st.session_state['deleted_domains'] = {}

    # Table for root domains
    roots = [r for r in st.session_state.get('root_options', []) if r not in st.session_state.get('deleted_roots', set())]
    if roots:
        st.write("### Root Domains")
        # Table header
        header_col1, header_col2 = st.columns([3, 4])
        with header_col1:
            st.markdown("**Root Domain**")
        with header_col2:
            st.markdown("**Action**")

        for idx, root in enumerate(roots):
            root_url = f"https://www.{root}.com"
            col1, col2 = st.columns([3, 4])
            with col1:
                st.markdown(f"[{root_url}]({root_url})")
            with col2:
                vcol, dcol, bcol = st.columns([1, 1, 3])
                with vcol:
                    st.markdown(f'<a href="{root_url}" target="_blank">🔗</a>', unsafe_allow_html=True)
                with dcol:
                    del_key = f"del_root_{idx}"
                    if st.button("🗑️", key=del_key, help="Delete root domain"):
                        st.session_state['deleted_roots'].add(root)
                        st.rerun()
                with bcol:
                    find_key = f"find_domains_{idx}"
                    if root not in st.session_state['expanded_domains']:
                        if st.button("Find all domains", key=find_key):
                            with st.spinner(f"Searching for all www.{root}.* domains..."):
                                domains = get_all_domains(root)
                            st.session_state['expanded_domains'][root] = domains
                            st.session_state['deleted_domains'][root] = set()
                            st.rerun()
                    else:
                        st.write(":arrow_down: Domains:")
                        for didx, domain in enumerate(st.session_state['expanded_domains'][root]):
                            if domain in st.session_state['deleted_domains'].get(root, set()):
                                continue
                            dcol1, dcol2, dcol3 = st.columns([4,1,1])
                            with dcol1:
                                st.markdown(f"[{domain}]({domain})")
                            with dcol2:
                                st.markdown(f'<a href="{domain}" target="_blank">🔗</a>', unsafe_allow_html=True)
                            with dcol3:
                                del_domain_key = f"del_domain_{root}_{didx}"
                                if st.button("🗑️", key=del_domain_key, help="Delete this domain"):
                                    st.session_state['deleted_domains'][root].add(domain)
                                    st.rerun()
    else:
        st.info("No root domains to display. Please search for a company.")

if __name__ == "__main__":
    main() 