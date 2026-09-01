import logging
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

log = logging.getLogger("tml.network")

MAX_DOWNLOAD_BYTES = 400 * 1024 * 1024


class DownloadCancelled(Exception):
    pass


def _verify_arg():
    pinned = os.environ.get("TML_CA_BUNDLE")
    return pinned if pinned else True


def get_session():
    
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    s.verify = _verify_arg()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    # requests.Session() mounts a default http:// adapter internally;
    # remove it so a redirect to plain HTTP raises InvalidSchema instead
    # of silently downgrading the connection. This app only ever
    # constructs https:// URLs.
    s.adapters.pop("http://", None)
    return s


def resolve_redirect(url, timeout=20):
  
    session = get_session()
    with session.get(url, timeout=timeout, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        return r.url


def fetch_bytes(url, max_bytes=2 * 1024 * 1024, timeout=20):
    with get_session().get(url, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise ValueError(f"Response from {url} exceeded {max_bytes} bytes")
        return bytes(buf)


def download_file(url, dest_path, progress_cb=None, timeout=30, should_cancel=None):
    tmp_path = dest_path + ".part"
    try:
        with get_session().get(url, timeout=timeout, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or None
            done = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if should_cancel and should_cancel():
                        raise DownloadCancelled(url)
                    if not chunk:
                        continue
                    done += len(chunk)
                    if done > MAX_DOWNLOAD_BYTES:
                        raise ValueError(f"{url} exceeded the {MAX_DOWNLOAD_BYTES} byte safety limit")
                    f.write(chunk)
                    if progress_cb:
                        progress_cb(done, total)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    os.replace(tmp_path, dest_path)
    log.info("Downloaded %s -> %s (%d bytes)", url, dest_path, os.path.getsize(dest_path))
    return dest_path
