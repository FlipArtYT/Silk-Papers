from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
import httpx

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

@dataclass
class WebsiteData:
    url: str
    page_text: str
    title: str = "No title"
    # prev_url: str = None

class WebScraper:
    def __init__(self):
        self.pages: list[WebsiteData] = []
    
    async def default_updater(self, m):
        pass
    
    async def scrape_pages_from_url(self, start_url:str, depth:int=2, max_websites:int=10, stay_on_domain:bool=False, on_update=None) -> list[WebsiteData]:
        self.pages = []
        links = set()
        max_scraped_websites = max_websites
        queue: list[tuple[str, int]] = [(start_url, depth)]

        while len(self.pages) < max_scraped_websites and len(queue) > 0:
            url, depth = queue.pop(0)

            if url in links:
                 continue
            
            links.add(url)

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)

                if response.status_code == 200:
                    if not "text/html" in response.headers.get('content-type', ''):
                        page_text = response.text
                        self.pages.append(WebsiteData(url=url, page_text=page_text, title="No Title provided"))
                        await on_update({"task":"SCRAPE", "status":"LOG", "url":url})
                        continue

                    soup = BeautifulSoup(response.text, "html.parser")
                    soup_links = soup.find_all("a", href=True)
                    website_title = soup.title.string

                    print("Found: " + bcolors.OKBLUE + url + bcolors.ENDC + " Links: " + bcolors.OKGREEN + str(len(soup_links)) + bcolors.ENDC)
                    await on_update({"task":"SCRAPE", "status":"SUCCESS", "url":url})

                    for script_or_style in soup(["script", "style"]):
                        script_or_style.decompose()
                    
                    # Get plain text page
                    page_text = soup.get_text(separator=" ", strip=True)

                    self.pages.append(WebsiteData(url=url, page_text=page_text, title=website_title))

                    if depth > 0:
                        for link in soup_links:
                            full_url_link = urljoin(url, link["href"])

                            if full_url_link in links:
                                continue
                            elif "#" in full_url_link:
                                continue
                            elif len(self.pages) > 0 and stay_on_domain:
                                if not urlparse(self.pages[0].url).netloc == urlparse(full_url_link).netloc:
                                    continue

                            queue.append((full_url_link, depth - 1))

            except Exception as e:
                print(bcolors.FAIL + "Failed to scrape: " + url + ": " + str(e) + bcolors.ENDC)
                await on_update({"task":"SCRAPE", "status":"FAIL", "url":url})
                continue
        
        return self.pages