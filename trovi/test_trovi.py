import json
import os
from urllib.parse import urljoin
import requests

username = os.environ["TEST_TROVI_USERNAME"]
password = os.environ["TEST_TROVI_PASSWORD"]
client_id = os.environ["TEST_TROVI_CLIENT_ID"]
client_secret = os.environ["TEST_TROVI_CLIENT_SECRET"]


def get_kc_token():
    url = "https://auth.dev.chameleoncloud.org/auth/realms/chameleon/protocol/openid-connect/token"

    payload = {
        "username": username,
        "grant_type": "password",
        "password": password,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"content-type": "application/x-www-form-urlencoded"}

    response = requests.post(url, data=payload, headers=headers)

    return response.json()


def get_trovi_token():
    kc_token = get_kc_token()["access_token"]

    url = "http://localhost:8808/token"

    payload = {
        "grant_type": "token_exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "scope": "artifacts:read artifacts:write",
        "subject_token": kc_token,
    }
    response = requests.post(url, json=payload)
    return response.json()


def make_authenticated_trovi_request(path, token=None, method="GET", payload=None):
    url = urljoin("http://localhost:8808/", path)
    query = {
        "access_token": token,
    }

    if method == "GET":
        response = requests.get(url, params=query)
    elif method == "POST":
        response = requests.post(url, params=query, json=payload)
    return response


def pretty_print(res):
    print(res.status_code)
    print(json.dumps(res.json(), indent=4))


def main():
    # 5 min lived token
    token = get_trovi_token()["access_token"]

    # list artifacts
    res = make_authenticated_trovi_request("artifacts", token=token)
    print("Existing artifacts")
    pretty_print(res)

    # create artifact
    artifact_body = {
        "tags": [],
        "authors": [
            {
                "full_name": "first",
                "affiliation": "UChicago",
                "email": username,
            }
        ],
        "reproducibility": {},
        "title": "my artifact",
        "short_description": "demo",
        "long_description": "demo",
        "owner_urn": f"urn:trovi:user:chameleon:{username}",
        "visibility": "private",
    }
    res = make_authenticated_trovi_request(
        "artifacts", token=token, method="POST", payload=artifact_body
    )
    print("Created artifact")
    pretty_print(res)

    # list artifacts again
    res = make_authenticated_trovi_request("artifacts", token=token)
    print("Listing public artifacts")
    pretty_print(res)

    # list public artifacts (no token)
    res = make_authenticated_trovi_request("artifacts", token=None)
    pretty_print(res)


if __name__ == "__main__":
    main()
