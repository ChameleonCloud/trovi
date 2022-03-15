from urllib.parse import urlparse


def url_to_fqdn(url: str) -> str:
    """
    Extracts the FQDN from a URL.
    """
    return urlparse(url).netloc
