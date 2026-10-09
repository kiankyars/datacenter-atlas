"""Serve a built site the way GitHub Pages serves this project site.

CI and the browser tests use this server instead of ``python -m http.server``, because the
standard server answers some requests that GitHub Pages refuses, and so lets tests pass for URLs
that are broken in production. Like GitHub Pages, this server:

- serves the site only under its sub-path (``/datacenter-atlas/`` by default);
- answers a directory URL with its ``index.html``, or else its ``index.json``, and never with a
  generated directory listing: a directory without either is a 404;
- redirects a directory URL that lacks its trailing slash (301), and serves ``/page`` from
  ``page.html`` when only that exists;
- answers a missing path with the site's own ``404.html`` and status 404;
- sends ``Access-Control-Allow-Origin: *`` and GitHub's media types (for example
  ``application/geo+json`` for GeoJSON and ``application/octet-stream`` for NDJSON and SQLite).

Usage (standard library only)::

    python site/e2e/pages_server.py --directory _site --port 8000
    # then open http://127.0.0.1:8000/datacenter-atlas/
"""

from __future__ import annotations

import argparse
import http.server
import io
import os
import posixpath
import sys
import urllib.parse

DEFAULT_SUB_PATH = "/datacenter-atlas/"
INDEX_FILES = ("index.html", "index.json")
# Media types as GitHub Pages sends them (checked against the live site on 2026-10-09).
MEDIA_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".geojson": "application/geo+json",
    ".gif": "image/gif",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".md": "text/markdown; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xml": "application/xml",
    ".zip": "application/x-zip-compressed",
}
DEFAULT_MEDIA_TYPE = "application/octet-stream"
FALLBACK_NOT_FOUND = b"<!doctype html><title>Page not found</title><h1>404</h1>\n"


def normalize_sub_path(value: str) -> str:
    """'/datacenter-atlas/' for 'datacenter-atlas', '/datacenter-atlas' or '/datacenter-atlas/'."""
    parts = [part for part in str(value).split("/") if part]
    return "/" + "/".join(parts) + "/" if parts else "/"


class PagesRequestHandler(http.server.SimpleHTTPRequestHandler):
    """``SimpleHTTPRequestHandler`` with GitHub Pages' rules for one project site."""

    server_version = "AtlasPagesServer/1"
    sub_path = DEFAULT_SUB_PATH
    quiet = True

    def __init__(self, *args, sub_path: str | None = None, quiet: bool | None = None, **kwargs):
        # BaseHTTPRequestHandler handles the request inside __init__, so set options first.
        if sub_path is not None:
            self.sub_path = normalize_sub_path(sub_path)
        if quiet is not None:
            self.quiet = quiet
        super().__init__(*args, **kwargs)

    # -- path mapping ----------------------------------------------------------------------

    def _site_relative(self, url_path: str) -> str | None:
        """The path inside the site for a request path, or None when it is outside the site.

        Dot segments are resolved first, as a browser or CDN would, so ``/atlas/../x`` is ``/x``.
        """
        path = urllib.parse.unquote(urllib.parse.urlsplit(url_path).path, errors="surrogatepass")
        trailing = path.endswith("/")
        path = posixpath.normpath("/" + path.lstrip("/"))
        if trailing and path != "/":
            path += "/"
        prefix = self.sub_path.rstrip("/")
        if self.sub_path == "/":
            return path
        if path == prefix:
            return "/"
        if not path.startswith(self.sub_path):
            return None
        return path[len(prefix):]

    def translate_path(self, path: str) -> str:
        relative = self._site_relative(path)
        if relative is None:
            return os.path.join(self.directory, ".outside-the-site")
        # Same normalisation as http.server: drop empty, "." and ".." segments.
        words = [word for word in posixpath.normpath(relative).split("/") if word]
        result = self.directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            result = os.path.join(result, word)
        return result

    # -- responses -------------------------------------------------------------------------

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        return MEDIA_TYPES.get(os.path.splitext(path)[1].lower(), DEFAULT_MEDIA_TYPE)

    def list_directory(self, path):
        """GitHub Pages never lists a directory."""
        return self._not_found()

    def _not_found(self):
        page = os.path.join(self.directory, "404.html")
        body = FALLBACK_NOT_FOUND
        if self._site_relative(self.path) is not None and os.path.isfile(page):
            with open(page, "rb") as handle:
                body = handle.read()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return io.BytesIO(body)

    def send_head(self):
        parts = urllib.parse.urlsplit(self.path)
        relative = self._site_relative(self.path)
        if relative is None or "\x00" in relative:
            return self._not_found()
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not parts.path.endswith("/"):
                location = urllib.parse.urlunsplit(("", "", parts.path + "/", parts.query, ""))
                self.send_response(301)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            for name in INDEX_FILES:
                candidate = os.path.join(path, name)
                if os.path.isfile(candidate):
                    path = candidate
                    break
            else:
                return self._not_found()
        elif parts.path.endswith("/"):
            return self._not_found()
        elif not os.path.isfile(path):
            if not os.path.isfile(path + ".html"):
                return self._not_found()
            path += ".html"
        try:
            handle = open(path, "rb")
        except OSError:
            return self._not_found()
        try:
            size = os.fstat(handle.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Length", str(size))
            self.end_headers()
            return handle
        except Exception:
            handle.close()
            raise

    def log_message(self, format: str, *args) -> None:
        if not self.quiet:
            super().log_message(format, *args)


def make_server(
    directory: str | os.PathLike[str],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    sub_path: str = DEFAULT_SUB_PATH,
    quiet: bool = True,
) -> http.server.ThreadingHTTPServer:
    """A threading server for ``directory`` (``port`` 0 picks a free port)."""
    root = os.fspath(directory)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"{root} is not a directory")

    def handler(*args, **kwargs):
        return PagesRequestHandler(*args, directory=root, sub_path=sub_path, quiet=quiet, **kwargs)

    server = http.server.ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def base_url(server: http.server.ThreadingHTTPServer, sub_path: str = DEFAULT_SUB_PATH) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}{normalize_sub_path(sub_path)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--directory", default="_site", help="built site to serve (default: _site)")
    parser.add_argument("--bind", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    parser.add_argument(
        "--sub-path", default=DEFAULT_SUB_PATH, help=f"URL prefix of the site (default: {DEFAULT_SUB_PATH})"
    )
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args(argv)
    try:
        server = make_server(
            args.directory, host=args.bind, port=args.port, sub_path=args.sub_path, quiet=not args.verbose
        )
    except (OSError, FileNotFoundError) as error:
        print(f"pages_server: {error}", file=sys.stderr)
        return 1
    print(f"Serving {os.path.abspath(args.directory)} at {base_url(server, args.sub_path)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
