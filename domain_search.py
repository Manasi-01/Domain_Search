# Google search custom API is directly asked to the user 
# Used Google custom API and openai 

import streamlit as st
import requests
import tldextract
import time
import os
from dotenv import load_dotenv
from collections import Counter
# OpenAI imports
from openai import OpenAI

load_dotenv()
# Get Search Engine ID from environment variables
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

# Initialize Google Search API key in session state
if 'google_api_key' not in st.session_state:
    st.session_state.google_api_key = ""

# Search Google Custom Search API for a query and return links
def search_google(query, num=100, show_full_response=False):
    """
    Search Google using Custom Search API and return links
    
    Args:
        query (str): Search query
        num (int): Maximum number of results to return
        show_full_response (bool): If True, prints and returns the full API response
        
    Returns:
        list: List of URLs or full API response if show_full_response is True
    """
    url = "https://www.googleapis.com/customsearch/v1"
    
    # Check if we have the required API credentials
    if not st.session_state.google_api_key:
        st.error("API Key not found. Please enter your Google Search API Key in the sidebar.")
        st.stop()
        
    if not GOOGLE_SEARCH_ENGINE_ID:
        st.error("Error: Google Search Engine ID not found in environment variables")
        st.error("Please set GOOGLE_SEARCH_ENGINE_ID in your .env file")
        return []
    
    custom_search_engine_id = GOOGLE_SEARCH_ENGINE_ID
    
    all_links = []
    all_responses = []  # To store full API responses
    max_results_per_request = 10
    max_requests = min(10, (num // max_results_per_request) + 1)  # Limit to 10 requests max
    
    for i in range(max_requests):
        start_index = i * max_results_per_request + 1
        if start_index > 100:  # Google API limit
            print("Reached Google API's maximum result limit (100 results)")
            break
            
        params = {
            "key": st.session_state.google_api_key,
            "cx": custom_search_engine_id,
            "q": query,
            "num": min(max_results_per_request, num - len(all_links)),
            "start": start_index
        }
        
        try:
            print(f"\n=== Making API Request (Page {i+1}) ===")
            print(f"Query: {query}")
            print(f"Start Index: {start_index}")
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                all_responses.append(data)  # Store full response
                
                # Print search information
                search_info = data.get('searchInformation', {})
                print(f"\nSearch Information:")
                print(f"- Total Results: {search_info.get('totalResults', 'N/A')}")
                print(f"- Search Time: {search_info.get('searchTime', 'N/A')} seconds")
                
                # Print query information
                queries = data.get('queries', {})
                if 'request' in queries and queries['request']:
                    req = queries['request'][0]
                    print(f"\nQuery Details:")
                    print(f"- Search Terms: {req.get('searchTerms', 'N/A')}")
                    print(f"- Start Index: {req.get('startIndex', 'N/A')}")
                    print(f"- Count: {req.get('count', 'N/A')}")
                
                # Process and print items
                items = data.get('items', [])
                print(f"\nFound {len(items)} items in this batch:")
                
                links = []
                for idx, item in enumerate(items, 1):
                    link = item.get('link', 'No link')
                    
                    print(f"URL: {link}")
                    
                    # Print additional metadata if available
                    if 'pagemap' in item:
                        pagemap = item['pagemap']
                        if 'metatags' in pagemap and pagemap['metatags']:
                            meta = pagemap['metatags'][0]
                            
                            for key in ['og:site_name', 'og:type', 'og:description']:
                                if key in meta:
                                    print(f"- {key}: {meta[key][:100]}...")
                    
                    links.append(link)
                
                all_links.extend(links)
                
                # If we got fewer results than requested, we've reached the end
                if len(links) < max_results_per_request:
                    print("\nReached the end of search results")
                    break
                    
                # Add delay to respect rate limits
                if i < max_requests - 1:
                    time.sleep(1)  # Increased delay to be safer with rate limits
                    
            else:
                print(f"\n=== API Error ===")
                print(f"Status Code: {response.status_code}")
                print(f"Response: {response.text}")
                print(f"Query: {query}")
                print(f"API Key present: {'Yes' if GOOGLE_SEARCH_API_KEY else 'No'}")
                break
                
        except Exception as e:
            print(f"\n=== Exception ===")
            print(f"Error calling Google Search API: {e}")
            import traceback
            traceback.print_exc()
            break
    
    if show_full_response:
        print("\n=== Full API Response ===")
        import json
        print(json.dumps(all_responses, indent=2, ensure_ascii=False))
        return all_responses
            
    return all_links[:num]  # Return only the requested number of results

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
        links = search_google(query, num=100)
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


@st.cache_data(show_spinner=False)
def filter_social_and_news_domains_llm(domains, company_name=""):
    if not openai_client or not domains:
        return domains 
    
    prompt = f"""You are a domain classification expert analyzing domains for the company: "{company_name}".

Your task is to identify and flag domains that should be EXCLUDED from a company domain search.

COMPANY CONTEXT: The target company is "{company_name}". You are looking for domains that belong to this company or its subsidiaries/regional offices.

Important Note: The domains can also be named other than the company name do not remove it. 

EXCLUDE THESE CATEGORIES ONLY:
1. Social Media Platforms: Facebook, Twitter, Instagram, LinkedIn, TikTok, YouTube, Pinterest, Snapchat, Reddit, WhatsApp, Telegram, Discord, etc.
2. News & Media Outlets: CNN, BBC, Reuters, Associated Press, New York Times, Washington Post, Fox News, NBC, ABC, CBS, CNBC, Bloomberg, etc.
3. Online Encyclopedias: Wikipedia, Britannica, Fandom wikis, etc.
4. Search Engines: Google, Bing, Yahoo, DuckDuckGo, Baidu, etc.
5. Public Knowledge Directories: IMDB, AllMusic, MusicBrainz, etc.
6. General Information Sites: About.com, eHow, WikiHow, etc.
7. Government Websites: .gov domains, official government portals
8. Educational Institutions: Universities, schools, .edu domains
9. Non-profit Organizations: Major NGOs, charities, foundations
10. Public Forums & Communities: Stack Overflow, Quora, forums, discussion boards
11. File Sharing & Cloud Storage: Dropbox, Google Drive, OneDrive, etc.
12. Generic Service Providers: Email services, web hosting, domain registrars
13. General Technology Platforms: GitHub, GitLab, cloud platforms (AWS, Azure, GCP)
14. Online Marketplaces: Amazon, eBay, Alibaba, etc.
15. Job portals: LinkedIn, Indeed, Glassdoor, etc.
16. Trade related sites: Alibaba, Amazon, eBay, etc.
17. Money related sites: PayPal, Stripe, etc.

INSTRUCTIONS:
- Be STRICT about excluding the 17 categories above
- Be PROTECTIVE of any domain that could be a legitimate company domain variation
- When in doubt about a company domain variation, DO NOT flag it
- Only flag domains that clearly belong to the excluded categories and have NO relation to "{company_name}"

FORMAT: Return ONLY a comma-separated list of domain names (without .com) that should be EXCLUDED. No explanations, no additional text.

EXAMPLES FOR COMPANY "Sonepar":
- linkedin, wikipedia, amazon → These should be flagged (social media, encyclopedia, marketplace)
- microsoft, tesla, apple → These should be flagged (unrelated companies)
- sonepar, soneparusa, sonepar-us, soneparcanada, soneparinc → These should NOT be flagged (company variations)

DOMAINS TO ANALYZE:
{', '.join([d + '.com' for d in domains])}

RESPONSE (comma-separated list of domains to EXCLUDE):"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": "You are a precise domain classification expert. Follow instructions exactly and return only the requested format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for more consistent results
            max_tokens=500
        )
        answer = response.choices[0].message.content.strip().lower()
        print(f"OpenAI batch response: {answer}")
        
        # Parse the response to get excluded domains
        excluded_domains = [d.strip().lower() for d in answer.split(',') if d.strip()]
        
        # Filter out the excluded domains
        filtered_domains = [d for d in domains if d.lower() not in excluded_domains]
        
        print(f"LLM filtered: {len(domains)} → {len(filtered_domains)} (removed {len(excluded_domains)})")
        print(f"LLM excluded: {excluded_domains}")
        
        return filtered_domains
        
    except Exception as e:
        print(f"OpenAI batch error: {e}")
        # Return original domains if there's an error
        return domains

def main():
    st.title("Company Domain Finder")
    
    # API Key Input Section
    st.sidebar.header("API Configuration")
    if 'google_api_key' not in st.session_state:
        st.session_state.google_api_key = ""
    
    api_key = st.sidebar.text_input("Enter Google Search API Key:", 
                                 value=st.session_state.google_api_key,
                                 type="password",
                                 help="Get your API key from Google Cloud Console")
    
    if api_key != st.session_state.google_api_key:
        st.session_state.google_api_key = api_key
        st.sidebar.success("API Key updated!")
    
    # Main App
    st.write("Enter a company name to find all its domains using Google.")
    company = st.text_input("Enter the company name:")
    
    if not st.session_state.google_api_key:
        if company:  # Only show error if user tries to search without API key
            st.error("Please enter your Google Search API Key in the sidebar to begin searching.")
        return  # Exit early if no API key is provided
        
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
                # Create more targeted search queries to find company domains
                search_queries = [
                    f'"{company}" site:*.com',  # Official company sites
                    f'"{company}" official website',  # Official websites
                    f'"{company}" corporate site',  # Corporate sites
                    f'"{company}" company domain',  # Company domains
                    f'"{company}" headquarters',  # Company headquarters
                ]
                
                all_links = []
                for query in search_queries:
                    links = search_google(query, num=10)
                    all_links.extend(links)
                    time.sleep(0.2)  # Small delay between queries
                
                # Remove duplicates while preserving order
                unique_links = []
                seen = set()
                for link in all_links:
                    if link not in seen:
                        unique_links.append(link)
                        seen.add(link)
                
                roots = extract_root_domains(unique_links)
                if not roots:
                    st.warning("No root domains found in search results.")
                else:
                    root_counts = Counter(roots)
                    most_common = [r for r, _ in root_counts.most_common()]
                    with st.spinner("Filtering out social media and news domains"):
                        filtered_roots = filter_social_and_news_domains_llm(most_common, company)
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