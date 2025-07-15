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
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

# Search Google Custom Search API for a query and return links
def search_google(query, num=400):
    # Using Google Custom Search API
    # To set up a Custom Search Engine:
    # 1. Go to https://cse.google.com/cse/
    # 2. Create a new search engine
    # 3. Set it to search the entire web
    # 4. Get your Search Engine ID and replace the cx parameter below
    
    url = "https://www.googleapis.com/customsearch/v1"
    
    # Check if we have the required API credentials
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        print("Error: Google Search API Key or Search Engine ID not found in environment variables")
        print("Please set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in your .env file")
        return []
    
    custom_search_engine_id = GOOGLE_SEARCH_ENGINE_ID
    
    all_links = []
    max_results_per_request = 10
    max_requests = min(10, (num // max_results_per_request) + 1)  # Limit to 10 requests max
    
    for i in range(max_requests):
        start_index = i * max_results_per_request + 1
        if start_index > 100:  # Google API limit
            break
            
        params = {
            "key": GOOGLE_SEARCH_API_KEY,
            "cx": custom_search_engine_id,
            "q": query,
            "num": max_results_per_request,
            "start": start_index
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                links = [item["link"] for item in data.get("items", [])]
                all_links.extend(links)
                
                # If we got fewer results than requested, we've reached the end
                if len(links) < max_results_per_request:
                    break
                    
                # Add delay to respect rate limits
                if i < max_requests - 1:
                    time.sleep(0.1)
                    
            else:
                print(f"Google Search API error: {response.status_code}")
                print(f"Response: {response.text}")
                print(f"Query: {query}")
                print(f"API Key present: {'Yes' if GOOGLE_SEARCH_API_KEY else 'No'}")
                break
                
        except Exception as e:
            print(f"Error calling Google Search API: {e}")
            break
            
    return all_links[:num]  # Return only the requested number of results

# Extract root domains from URLs using tldextract
def extract_root_domains(links):
    roots = []
    for link in links:
        ext = tldextract.extract(link)
        if ext.domain and ext.suffix:
            # Handle special domain names like team.blue
            domain = ext.domain.lower()
            # Check if the domain itself might be a company name
            if ext.suffix and '.' in ext.suffix:
                # Handle cases like team.blue, team.red, etc.
                if domain not in roots:
                    roots.append(domain)
            # Also add the full domain (domain + suffix) as a potential match
            full_domain = f"{domain}.{ext.suffix.lower()}"
            if full_domain not in roots:
                roots.append(full_domain)
    return roots

# Extract all www.<root>.* domains and return full URLs
def get_all_domains(root):
    found_domains = set()
    excluded_tlds = set(["com"])
    found_domains.add(f"https://www.{root}.com")
    while True:
        query = f"site:www.{root}.*" + (" " + " ".join(f"-{tld}" for tld in sorted(excluded_tlds)) if excluded_tlds else "")
        links = search_google(query, num=400)
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
# Pre-filter domains using pattern matching before OpenAI call
def pre_filter_domains(domains, company_name=""):
    # Common patterns for domains we want to exclude
    exclude_patterns = [
        # Social media
        'facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'tiktok', 'pinterest', 'snapchat', 
        'reddit', 'discord', 'whatsapp', 'telegram', 'tumblr', 'flickr', 'vimeo', 'vine',
        
        # News and media
        'cnn', 'bbc', 'reuters', 'ap', 'nytimes', 'wsj', 'washingtonpost', 'guardian', 'times',
        'news', 'article', 'blog', 'press', 'media', 'journalist', 'magazine', 'newspaper',
        
        # Search engines
        'google', 'bing', 'yahoo', 'duckduckgo', 'baidu', 'search', 'ask', 'dogpile',
        
        # Knowledge bases
        'wikipedia', 'wikimedia', 'britannica', 'imdb', 'allmusic', 'musicbrainz', 'fandom',
        'wiki', 'encyclopedia', 'reference', 'dictionary', 'thesaurus',
        
        # Government and education
        'edu', 'university', 'college', 'school', 'academic', 'research', 'institute',
        
        # Generic services
        'email', 'mail', 'hosting', 'server', 'cloud', 'storage', 'backup', 'domain',
        'whois', 'dns', 'ssl', 'cert', 'security', 'firewall', 'antivirus',
        
        # Marketplaces and shopping
        'amazon', 'ebay', 'alibaba', 'etsy', 'shopify', 'store', 'shop', 'marketplace',
        'ecommerce', 'retail', 'buy', 'sell', 'cart', 'checkout', 'payment',
        
        # Tech platforms
        'github', 'gitlab', 'stackoverflow', 'aws', 'azure', 'gcp', 'digitalocean',
        'heroku', 'netlify', 'vercel', 'cloudflare', 'jsdelivr', 'unpkg',
        
        # File sharing
        'dropbox', 'drive', 'onedrive', 'icloud', 'box', 'mega', 'mediafire',
        'file', 'download', 'upload', 'share', 'sync',
        
        # Common generic words
        'free', 'online', 'web', 'site', 'page', 'home', 'www', 'http', 'https',
        'test', 'demo', 'example', 'sample', 'tmp', 'temp', 'dev', 'staging',
        'api', 'cdn', 'static', 'assets', 'images', 'img', 'photos', 'pics'
    ]
    
    filtered_domains = []
    excluded_domains = []
    company_lower = company_name.lower() if company_name else ""
    
    for domain in domains:
        domain_lower = domain.lower()
        should_exclude = False
        
        # PROTECTION: Never exclude domains that are clearly company variations
        is_company_domain = False
        if company_lower and len(company_lower) > 2:
            # Check if domain starts with company name or contains it as main part
            if (domain_lower.startswith(company_lower) or 
                domain_lower.replace('-', '').startswith(company_lower) or
                (company_lower in domain_lower and 
                 (domain_lower.startswith(company_lower) or 
                  domain_lower.replace('-', '').startswith(company_lower) or
                  domain_lower.endswith(company_lower)))):
                is_company_domain = True
        
        # If it's a company domain, don't exclude it
        if is_company_domain:
            filtered_domains.append(domain)
            continue
            
        # Check against exclude patterns
        for pattern in exclude_patterns:
            if pattern in domain_lower:
                should_exclude = True
                break
        
        # Additional checks for common patterns
        if not should_exclude:
            # Check for numeric-only domains or very short domains
            if domain_lower.isdigit() or len(domain_lower) <= 2:
                should_exclude = True
            
            # Check for domains with common file extensions
            if any(ext in domain_lower for ext in ['.jpg', '.png', '.gif', '.pdf', '.doc', '.zip']):
                should_exclude = True
            
            # Check for domains that are mostly numbers
            if sum(c.isdigit() for c in domain_lower) > len(domain_lower) * 0.7:
                should_exclude = True
        
        if should_exclude:
            excluded_domains.append(domain)
        else:
            filtered_domains.append(domain)
    
    print(f"Pre-filter: {len(domains)} → {len(filtered_domains)} (removed {len(excluded_domains)})")
    print(f"Pre-filter excluded: {excluded_domains}")
    
    return filtered_domains



@st.cache_data(show_spinner=False)
def filter_social_and_news_domains_llm(domains, company_name=""):
    if not openai_client or not domains:
        return domains  # If OpenAI not configured, don't filter
    
    # First, apply pre-filtering
    pre_filtered_domains = pre_filter_domains(domains, company_name)
    
    if not pre_filtered_domains:
        print("All domains were pre-filtered out!")
        return []
    
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
{', '.join([d + '.com' for d in pre_filtered_domains])}

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
        
        # Clean up the response and extract domain names
        flagged_domains = []
        if answer and answer != "none" and answer != "":
            # Split by comma and clean each domain
            raw_domains = answer.split(',')
            for domain in raw_domains:
                clean_domain = domain.strip().replace('.com', '').replace('.', '')
                if clean_domain and clean_domain != "none":
                    flagged_domains.append(clean_domain)
        
        # Return domains that are NOT flagged (i.e., keep the good ones)
        final_filtered_domains = [d for d in pre_filtered_domains if d not in flagged_domains]
        
        # Detailed debugging
        print(f"\n--- FILTERING RESULTS ---")
        print(f"Original domains: {domains}")
        print(f"Pre-filtered domains: {pre_filtered_domains}")
        print(f"OpenAI flagged for exclusion: {flagged_domains}")
        print(f"Final remaining domains: {final_filtered_domains}")
        print(f"Stats: {len(domains)} → {len(pre_filtered_domains)} → {len(final_filtered_domains)}")
        print(f"Total removed: {len(domains) - len(final_filtered_domains)}")
        print(f"--- END FILTERING ---\n")
        
        return final_filtered_domains
        
    except Exception as e:
        print(f"OpenAI batch error: {e}")
        # Return pre-filtered domains even if OpenAI fails
        return pre_filtered_domains

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