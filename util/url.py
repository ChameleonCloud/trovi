from urllib.parse import urlparse


def url_to_fqdn(url: str) -> str:
    """
    Extracts the FQDN from a URL.
    """
    return urlparse(url).netloc


def fqdn_to_nid(fqdn: str) -> str:
    return fqdn[:31].replace(".", "-")


def url_to_nid(url: str) -> str:
    return fqdn_to_nid(url_to_fqdn(url))
