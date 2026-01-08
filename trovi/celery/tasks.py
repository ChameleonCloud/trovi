import re
import time
from logging import getLogger
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import cloudscraper
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction

from trovi.models import AutoCrawledArtifact, CrawlRequest

LOG = getLogger(__name__)


scraper = cloudscraper.create_scraper()
class RobotsVerifier:
    def __init__(self):
        self.parsers = {}

    def can_fetch(self, url, user_agent="*"):
        domain = urlparse(url).netloc
        if domain not in self.parsers:
            self._load_robots(domain, url)
        try:
            return self.parsers[domain].can_fetch(user_agent, url)
        except Exception:
            return True

    def _load_robots(self, domain, url):
        scheme = urlparse(url).scheme
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = RobotFileParser()
        try:
            LOG.info(f"    [Robots] Checking: {robots_url}")
            resp = scraper.get(robots_url, timeout=5)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                parser.allow_all = True
        except Exception:
            parser.allow_all = True
        self.parsers[domain] = parser


robots_checker = RobotsVerifier()


def clean_text(text):
    return " ".join(text.split()).strip() if text else ""


def get_soup(url, respect_robots: bool):
    # Optional Robots Check
    if respect_robots and not robots_checker.can_fetch(url):
        LOG.warning(f"    [Blocked by Robots.txt] {url}")
        return None, None

    try:
        resp = scraper.get(url, timeout=10)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser"), resp.url
    except Exception as e:
        LOG.error(f"Error fetching {url}: {e}")
    return None, None


def parse_zenodo(soup):
    return {
        "authors": [
            m["content"] for m in soup.find_all("meta", attrs={"name": "citation_author"})
        ],
        "abstract": clean_text(
            soup.find("meta", attrs={"name": "description"})["content"]
        )
        if soup.find("meta", attrs={"name": "description"})
        else "",
        "tags": [
            m["content"] for m in soup.find_all("meta", attrs={"name": "citation_keywords"})
        ],
        "extra_info": f"DOI: {soup.find('meta', attrs={'name': 'citation_doi'})['content']}"
        if soup.find("meta", attrs={"name": "citation_doi"})
        else "",
    }


def parse_github(soup):
    return {
        "authors": [],
        "abstract": clean_text(soup.find("meta", property="og:description")["content"])
        if soup.find("meta", property="og:description")
        else "",
        "tags": [t.get_text().strip() for t in soup.find_all("a", class_="topic-tag")],
        "extra_info": "Source: GitHub Repository",
    }


def parse_acm(soup):
    data = {"authors": [], "abstract": "", "tags": [], "extra_info": ""}

    # Author parsing: Prefer detailed authors with affiliations
    detailed_author_elements = soup.select('div.contributors-with-details div[property="author"]')
    if detailed_author_elements:
        for author_element in detailed_author_elements:
            name_element = author_element.select_one('div[property="name"]')
            name = clean_text(name_element.get_text()) if name_element else None

            if not name:
                continue

            affiliation_element = author_element.select_one('div[property="affiliation"] span[property="name"]')
            affiliation = clean_text(affiliation_element.get_text()) if affiliation_element else None

            author_data = {"name": name}
            if affiliation:
                author_data["affiliation"] = affiliation

            data["authors"].append(author_data)

    # Fallback to simpler author list if detailed list not found or was empty
    if not data["authors"]:
        author_selectors = [
            'div.contributors span[property="author"]',
            '.loa__author-name span',
        ]
        for selector in author_selectors:
            authors = soup.select(selector)
            if authors:
                for author_element in authors:
                    name = clean_text(author_element.get_text())
                    if name and name not in data["authors"]:
                        data["authors"].append(name)
                if data["authors"]:
                    break  # Stop after finding authors with one selector

    # Abstract parsing (try multiple selectors)
    abstract_selectors = [
        'section[property="abstract"][data-type="main"] div[role="paragraph"]',
        'section#abstract div[role="paragraph"]',
        "div.abstractSection p",
    ]
    for selector in abstract_selectors:
        paragraphs = soup.select(selector)
        if paragraphs:
            data["abstract"] = "\n\n".join(
                [clean_text(p.get_text()) for p in paragraphs]
            )
            break  # Stop after the first successful selector

    # Fallback for abstract if still not found
    if not data["abstract"]:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            data["abstract"] = clean_text(meta_desc.get("content"))
        else:
            meta_og_desc = soup.find("meta", property="og:description")
            if meta_og_desc and meta_og_desc.get("content"):
                data["abstract"] = clean_text(meta_og_desc.get("content"))

        if not data["abstract"]:
            desc_header = soup.find("h2", id="sec-description")
            if desc_header and desc_header.find_next_sibling("p"):
                data["abstract"] = clean_text(
                    desc_header.find_next_sibling("p").get_text()
                )

    if soup.find("div", class_="article__index-terms"):
        data["tags"] = [
            clean_text(a.get_text())
            for a in soup.find("div", class_="article__index-terms").find_all("a")
        ]
    doi = soup.find("meta", attrs={"name": "publication_doi"})
    if doi:
        data["extra_info"] = f"DOI: {doi['content']}"
    return data


DOMAIN_PARSERS = {
    "zenodo.org": parse_zenodo,
    "github.com": parse_github,
    "dl.acm.org": parse_acm,
}


def _process_artifact(url, title, conference, respect_robots):
    LOG.info(f"  -> Processing Artifact: {title[:40]}...")

    soup, final_url = get_soup(url, respect_robots)
    if not soup:
        return

    final_url = final_url.rstrip("/")

    domain = urlparse(final_url).netloc.lower()

    data = {
        "conference": conference,
        "title": title,
        "source_url": final_url,
        "origin_type": "other",
        "abstract": "",
        "authors": [],
        "tags": [],
        "extra_info": "",
    }

    found_parser = False
    for key, parser_func in DOMAIN_PARSERS.items():
        if key in domain:
            data["origin_type"] = key
            try:
                data.update(parser_func(soup))
                found_parser = True
            except Exception as e:
                LOG.error(f"    ! Error parsing {key}: {e}")
            break

    if not found_parser:
        data["origin_type"] = domain
        data["extra_info"] = f"Resolved to external source: {domain}"

    with transaction.atomic():
        try:
            artifact = AutoCrawledArtifact.objects.get(source_url=data["source_url"])
            changed = False
            for field in ["conference", "title", "origin_type", "abstract", "authors", "tags", "extra_info"]:
                if getattr(artifact, field) != data[field]:
                    setattr(artifact, field, data[field])
                    changed = True
            if changed:
                artifact.approved = False
                artifact.save()
                LOG.info(f"Updated artifact: {data['title']}")
        except AutoCrawledArtifact.DoesNotExist:
            AutoCrawledArtifact.objects.create(
                source_url=data["source_url"],
                conference=data["conference"],
                title=data["title"],
                origin_type=data["origin_type"],
                abstract=data["abstract"],
                authors=data["authors"],
                tags=data["tags"],
                extra_info=data["extra_info"],
                approved=False,
            )
            LOG.info(f"Saved artifact: {data['title']}")


@shared_task(name="CrawlRequest")
def process_crawl_request(crawl_request_id: int, respect_robots: bool = True):
    """
    Processes a crawl request by finding and parsing artifacts from a given URL.
    """
    LOG.info(f"Processing crawl request {crawl_request_id}")
    try:
        crawl_request = CrawlRequest.objects.get(id=crawl_request_id)
        crawl_request.status = CrawlRequest.CrawlStatus.RUNNING
        crawl_request.save()

        start_url = crawl_request.url
        start_domain = urlparse(start_url).netloc
        LOG.info(f"Crawling {start_url}, staying on domain {start_domain}")

        queue = [start_url]
        visited_urls = set()
        visited_artifacts = set()

        while queue:
            url = queue.pop(0)
            if url in visited_urls:
                continue
            visited_urls.add(url)

            soup, current_url = get_soup(url, respect_robots)
            if not soup:
                continue

            path_parts = [p for p in urlparse(current_url).path.split("/") if p]
            conference = path_parts[0] if path_parts else "sysartifacts_main"
            conference = re.sub(
                r"\s*results\s*", "", conference, flags=re.IGNORECASE
            ).strip()

            # Find Artifacts
            for row in soup.find_all("tr"):
                link = row.find("a", string=re.compile(r"Artifact|Code", re.I))
                if not link:
                    continue

                href = link.get("href")
                if (
                    not href
                    or href.startswith(("mailto:", "git@", "#"))
                    or ("@" in href and "http" not in href)
                ):
                    continue

                full_link = urljoin(current_url, href)
                if full_link in visited_artifacts:
                    continue
                visited_artifacts.add(full_link)

                cols = row.find_all(["td", "th"])
                title = clean_text(cols[0].get_text()) if cols else "Unknown Title"

                _process_artifact(full_link, title, conference, respect_robots)

            # Find Next Pages
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_next_url = urljoin(current_url, href)
                if urlparse(full_next_url).netloc == start_domain:
                    if not any(
                        ext in full_next_url for ext in [".css", ".js", ".png", ".xml"]
                    ):
                        if (
                            full_next_url not in visited_urls
                            and full_next_url not in queue
                        ):
                            queue.append(full_next_url)

            time.sleep(0.1)

        crawl_request.status = CrawlRequest.CrawlStatus.COMPLETE
        crawl_request.save()
        LOG.info(f"Crawl request {crawl_request_id} complete")

    except CrawlRequest.DoesNotExist:
        LOG.error(f"Crawl request {crawl_request_id} not found")
    except Exception as e:
        LOG.error(f"Crawl request {crawl_request_id} failed: {e}")
        try:
            crawl_request = CrawlRequest.objects.get(id=crawl_request_id)
            crawl_request.status = CrawlRequest.CrawlStatus.FAILED
            crawl_request.crawled_data = f"Crawl failed: {str(e)}"
            crawl_request.save()
        except CrawlRequest.DoesNotExist:
            LOG.error(
                f"Could not update status for non-existent crawl request {crawl_request_id}"
            )
