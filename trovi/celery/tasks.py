import json
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
            resp = scraper.get(robots_url, timeout=3)
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


def sanitize_for_db(text):
    """Try to handle characters that MySQL utf8 cannot handle."""
    if not text:
        return text

    try:
        return text.encode('utf-8', 'ignore').decode('utf-8', 'ignore')
    except Exception:
        return text


def get_soup(url, respect_robots: bool, skip_robots_check: bool = False):
    if respect_robots and not skip_robots_check and not robots_checker.can_fetch(url):
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
            m["content"]
            for m in soup.find_all("meta", attrs={"name": "citation_author"})
        ],
        "abstract": (
            clean_text(soup.find("meta", attrs={"name": "description"})["content"])
            if soup.find("meta", attrs={"name": "description"})
            else ""
        ),
        "tags": [
            m["content"]
            for m in soup.find_all("meta", attrs={"name": "citation_keywords"})
        ],
        "extra_info": (
            f"DOI: {soup.find('meta', attrs={'name': 'citation_doi'})['content']}"
            if soup.find("meta", attrs={"name": "citation_doi"})
            else ""
        ),
    }


def parse_github(soup):
    return {
        "authors": [],
        "abstract": (
            clean_text(soup.find("meta", property="og:description")["content"])
            if soup.find("meta", property="og:description")
            else ""
        ),
        "tags": [t.get_text().strip() for t in soup.find_all("a", class_="topic-tag")],
        "extra_info": "Source: GitHub Repository",
    }


def parse_summary_page(soup):
    """Extract artifact description from sysartifacts summary pages."""
    description = ""

    description_heading = soup.find(
        ["h2", "h3"],
        string=re.compile(r"Description of the Artifact", re.IGNORECASE)
    )

    if description_heading:
        # Collect all paragraphs after the heading until the next heading
        content_parts = []
        current = description_heading.find_next()
        while current:
            if current.name in ["h2", "h3", "h4"]:
                break
            if current.name == "p":
                text = clean_text(current.get_text())
                if text:
                    content_parts.append(text)
            current = current.find_next_sibling()

        description = "\n\n".join(content_parts)

    return description


def parse_acm(soup):
    data = {"authors": [], "abstract": "", "tags": [], "extra_info": ""}

    # Author parsing: Prefer detailed authors with affiliations
    detailed_author_elements = soup.select(
        'div.contributors-with-details div[property="author"]'
    )
    if detailed_author_elements:
        for author_element in detailed_author_elements:
            name_element = author_element.select_one('div[property="name"]')
            name = clean_text(name_element.get_text()) if name_element else None

            if not name:
                continue

            affiliation_element = author_element.select_one(
                'div[property="affiliation"] span[property="name"]'
            )
            affiliation = (
                clean_text(affiliation_element.get_text())
                if affiliation_element
                else None
            )

            author_data = {"name": name}
            if affiliation:
                author_data["affiliation"] = affiliation

            data["authors"].append(author_data)

    # Fallback to simpler author list if detailed list not found or was empty
    if not data["authors"]:
        author_selectors = [
            'div.contributors span[property="author"]',
            ".loa__author-name span",
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


def _process_artifact(url, title, conference, respect_robots, crawl_request, summary_description="", errors=None):
    """Process artifact and return True if new, False if existing, None if failed."""
    if errors is None:
        errors = []

    LOG.info(f"  -> Processing Artifact: {title[:40]}...")

    # Only process artifacts from allowed external domains (those with parsers)
    artifact_domain = urlparse(url).netloc.lower()
    if artifact_domain not in DOMAIN_PARSERS:
        LOG.warning(f"  -> Skipping artifact from disallowed domain: {artifact_domain}")
        return None

    skip_robots = urlparse(url).netloc != "sysartifacts.github.io"
    soup, final_url = get_soup(url, respect_robots, skip_robots_check=skip_robots)
    if not soup:
        return None

    final_url = final_url.rstrip("/")

    domain = urlparse(final_url).netloc.lower()

    data = {
        "conference": conference,
        "title": title,
        "source_url": final_url,
        "origin_type": "other",
        "abstract": summary_description if summary_description else "",
        "authors": [],
        "tags": [],
        "extra_info": "",
    }

    found_parser = False
    for key, parser_func in DOMAIN_PARSERS.items():
        if key in domain:
            data["origin_type"] = key
            try:
                parser_data = parser_func(soup)
                # Preserve summary_description if it exists, otherwise use parsed data
                if summary_description:
                    parser_data["abstract"] = summary_description
                data.update(parser_data)
                found_parser = True
            except Exception as e:
                LOG.error(f"    ! Error parsing {key}: {e}")
            break

    if not found_parser:
        data["origin_type"] = domain
        data["extra_info"] = f"Resolved to external source: {domain}"

    data["title"] = sanitize_for_db(data["title"])
    data["abstract"] = sanitize_for_db(data["abstract"])
    data["extra_info"] = sanitize_for_db(data["extra_info"])
    if isinstance(data["authors"], list):
        data["authors"] = [sanitize_for_db(a) if isinstance(a, str) else a for a in data["authors"]]
    if isinstance(data["tags"], list):
        data["tags"] = [sanitize_for_db(t) for t in data["tags"]]

    with transaction.atomic():
        try:
            artifact = AutoCrawledArtifact.objects.get(source_url=data["source_url"])
            changed = False
            for field in [
                "conference",
                "title",
                "origin_type",
                "abstract",
                "authors",
                "tags",
                "extra_info",
            ]:
                if getattr(artifact, field) != data[field]:
                    setattr(artifact, field, data[field])
                    changed = True
            if changed:
                artifact.approved = False
                artifact.save()
                LOG.info(f"Updated artifact: {data['title']}")
            return False  # Existing artifact
        except AutoCrawledArtifact.DoesNotExist:
            AutoCrawledArtifact.objects.create(
                crawl_request=crawl_request,
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
            return True  # New artifact
        except Exception as e:
            error_msg = f"Error saving artifact {data.get('title', 'Unknown')}: {str(e)}"
            LOG.error(f"    ! {error_msg}")
            errors.append(error_msg)
            return None  # Error


@shared_task(name="CrawlRequest", time_limit=3600)  # 1 hour hard timeout
def process_crawl_request(crawl_request_id: int, respect_robots: bool = True):
    """
    Processes a crawl request by finding and parsing artifacts from a given URL.

    Currently this is specific to sysartifacts.github.io.
    """
    LOG.info(f"Processing crawl request {crawl_request_id}")
    try:
        crawl_request = CrawlRequest.objects.get(id=crawl_request_id)
        crawl_request.status = CrawlRequest.CrawlStatus.RUNNING
        crawl_request.save()

        start_url = crawl_request.url
        start_domain = urlparse(start_url).netloc.lower()

        if start_domain != "sysartifacts.github.io":
            error_msg = f"Unsupported domain: {start_domain}. Only sysartifacts.github.io is supported."
            LOG.error(f"Crawl request {crawl_request_id}: {error_msg}")
            crawl_request.status = CrawlRequest.CrawlStatus.FAILED
            crawl_request.crawled_data = json.dumps({
                "status": "error",
                "artifacts_found": {},
                "total_artifacts": 0,
                "new_artifacts": 0,
                "existing_artifacts": 0,
                "errors": [error_msg]
            })
            crawl_request.save()
            return

        LOG.info(f"Crawling {start_url}, staying on domain {start_domain}")
        LOG.info(f"Starting URL path: {urlparse(start_url).path}")

        queue = [start_url]
        visited_urls = set()
        visited_artifacts = set()
        artifacts_by_conference = {}
        new_artifacts_count = 0
        existing_artifacts_count = 0
        errors = []

        while queue:
            url = queue.pop(0)
            if url in visited_urls:
                continue
            visited_urls.add(url)

            queue_status = f"Queue size: {len(queue)}"
            LOG.info(f"  [Processing] {url} ({queue_status})")

            soup, current_url = get_soup(url, respect_robots)
            if not soup:
                continue

            path_parts = [p for p in urlparse(current_url).path.split("/") if p]
            conference = path_parts[0] if path_parts else "sysartifacts_main"
            conference = re.sub(
                r"\s*results\s*", "", conference, flags=re.IGNORECASE
            ).strip()
            LOG.info(f"    [Conference] Detected: {conference}, Path: {urlparse(current_url).path}")

            # If we're on the root page, extract all year-based links first
            if path_parts == [] or urlparse(current_url).path.rstrip("/") == "":
                year_links_found = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full_next_url = urljoin(current_url, href)
                    if urlparse(full_next_url).netloc == start_domain:
                        path_url = urlparse(full_next_url).path.rstrip("/")
                        path_segments = [p for p in path_url.split("/") if p]
                        is_year_link = bool(path_segments and re.match(r"^[a-z]+\d{4}$", path_segments[-1], re.I))
                        if is_year_link and full_next_url not in visited_urls and full_next_url not in queue:
                            year_links_found.append(full_next_url)

                if year_links_found:
                    for link in reversed(year_links_found):
                        queue.insert(0, link)
                    LOG.info(f"    [Root] Found {len(year_links_found)} year links: {year_links_found[:5]}")

            # Find Artifacts in table rows
            rows = soup.find_all("tr")
            if rows:
                LOG.info(f"    [Table] Found {len(rows)} table rows")
            for row in rows:
                link = row.find("a", string=re.compile(r"Artifact|Code", re.I))
                if link:
                    href = link.get("href")
                    if (
                        href
                        and not href.startswith(("mailto:", "git@", "#"))
                        and not ("@" in href and "http" not in href)
                    ):
                        full_link = urljoin(current_url, href)
                        if full_link not in visited_artifacts:
                            visited_artifacts.add(full_link)
                            artifacts_by_conference[conference] = artifacts_by_conference.get(conference, 0) + 1
                            cols = row.find_all(["td", "th"])
                            title = clean_text(cols[0].get_text()) if cols else "Unknown Title"
                            result = _process_artifact(
                                full_link, title, conference, respect_robots, crawl_request, "", errors
                            )
                            if result is True:
                                new_artifacts_count += 1
                            elif result is False:
                                existing_artifacts_count += 1

                # Look for artifact links in all table cells (for results pages)
                cols = row.find_all(["td", "th"])
                if len(cols) >= 3:
                    # Extract title from first column
                    title = clean_text(cols[0].get_text()) if cols else ""
                    summary_description = ""

                    # Look for links in columns 2-3 (badges and "Available at")
                    for col in cols[1:]:
                        for link in col.find_all("a", href=True):
                            href = link.get("href")

                            # Check if this is a summary link
                            if href and "summaries/" in href:
                                summary_url = urljoin(current_url, href)
                                summary_soup, _ = get_soup(summary_url, respect_robots, skip_robots_check=True)
                                if summary_soup:
                                    summary_description = parse_summary_page(summary_soup)

                            if (
                                href
                                and not href.startswith(("mailto:", "git@", "#"))
                                and not ("@" in href and "http" not in href)
                            ):
                                full_link = urljoin(current_url, href)
                                if full_link not in visited_artifacts:
                                    visited_artifacts.add(full_link)
                                    artifacts_by_conference[conference] = artifacts_by_conference.get(conference, 0) + 1
                                    result = _process_artifact(
                                        full_link, title, conference, respect_robots, crawl_request, summary_description, errors
                                    )
                                    if result is True:
                                        new_artifacts_count += 1
                                    elif result is False:
                                        existing_artifacts_count += 1

            current_is_year_page = len(path_parts) > 0 and re.match(r"^[a-z]+\d{4}$", path_parts[0], re.I)

            # Find Next Pages
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Skip anchor links (they don't contain new content)
                if href.startswith("#"):
                    continue

                full_next_url = urljoin(current_url, href)
                if urlparse(full_next_url).netloc == start_domain:
                    # Skip static assets and anchors
                    if any(ext in full_next_url for ext in [".css", ".js", ".png", ".xml"]):
                        continue

                    # Check if this is a year link (e.g., /atc2024, /fast2023, /eurosys2024)
                    path_url = urlparse(full_next_url).path.rstrip("/")
                    path_segments = [p for p in path_url.split("/") if p]
                    is_year_link = bool(path_segments and re.match(r"^[a-z]+\d{4}$", path_segments[-1], re.I))

                    # Check if this looks like a results page (handles both "result" and "results")
                    is_results_link = "result" in path_url.lower()

                    if is_results_link:
                        LOG.info(f"    [Results Link] Found results page: {full_next_url}")

                    # Add to queue if it's new and (is a year/results link OR hasn't been visited)
                    if full_next_url not in visited_urls and full_next_url not in queue:
                        if is_results_link and current_is_year_page:
                            LOG.info(f"  [Queue] Adding to front: {full_next_url}")
                            queue.insert(0, full_next_url)
                        else:
                            queue.append(full_next_url)

            time.sleep(0.1)

        LOG.info(f"Crawl request {crawl_request_id} complete. Queue had {len(queue)} remaining items")
        LOG.info(f"Visited {len(visited_urls)} URLs total")
        LOG.info(f"Found: {artifacts_by_conference}")

        crawl_request.status = CrawlRequest.CrawlStatus.COMPLETE
        crawl_request.crawled_data = json.dumps({
            "status": "success",
            "artifacts_found": artifacts_by_conference,
            "total_artifacts": sum(artifacts_by_conference.values()),
            "new_artifacts": new_artifacts_count,
            "existing_artifacts": existing_artifacts_count,
            "errors": errors if errors else []
        })
        crawl_request.save()
        LOG.info(f"Crawl request {crawl_request_id} complete. Found: {artifacts_by_conference}")

    except CrawlRequest.DoesNotExist:
        LOG.error(f"Crawl request {crawl_request_id} not found")
    except Exception as e:
        LOG.error(f"Crawl request {crawl_request_id} encountered error: {e}")
        try:
            crawl_request = CrawlRequest.objects.get(id=crawl_request_id)
            # Mark as COMPLETE even though there was an error, we did as much as we could
            crawl_request.status = CrawlRequest.CrawlStatus.COMPLETE
            crawl_request.crawled_data = json.dumps({
                "status": "error",
                "artifacts_found": artifacts_by_conference,
                "total_artifacts": sum(artifacts_by_conference.values()),
                "new_artifacts": new_artifacts_count,
                "existing_artifacts": existing_artifacts_count,
                "errors": [str(e)] + errors if errors else [str(e)]
            })
            crawl_request.save()
            LOG.info(f"Crawl request {crawl_request_id} completed with error handling")
        except CrawlRequest.DoesNotExist:
            LOG.error(
                f"Could not update status for non-existent crawl request {crawl_request_id}"
            )
