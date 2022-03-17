import re
from typing import Optional, Union, List, Mapping, Text, Tuple

from exceptions import PipenvUsageError
from project import TSource, Project
from requirementslib import Requirement
from urllib3 import util as urllib3_util
from utils import create_mirror_source, is_pypi_url


def prepare_pip_source_args(sources, pip_args=None):
    if pip_args is None:
        pip_args = []
    if sources:
        # Add the source to notpip.
        package_url = sources[0].get("url")
        if not package_url:
            raise PipenvUsageError("[[source]] section does not contain a URL.")
        pip_args.extend(["-i", package_url])
        # Trust the host if it's not verified.
        if not sources[0].get("verify_ssl", True):
            url_parts = urllib3_util.parse_url(package_url)
            url_port = f":{url_parts.port}" if url_parts.port else ""
            pip_args.extend(
                ["--trusted-host", f"{url_parts.host}{url_port}"]
            )
        # Add additional sources as extra indexes.
        if len(sources) > 1:
            for source in sources[1:]:
                url = source.get("url")
                if not url:  # not harmless, just don't continue
                    continue
                pip_args.extend(["--extra-index-url", url])
                # Trust the host if it's not verified.
                if not source.get("verify_ssl", True):
                    url_parts = urllib3_util.parse_url(url)
                    url_port = f":{url_parts.port}" if url_parts.port else ""
                    pip_args.extend(
                        ["--trusted-host", f"{url_parts.host}{url_port}"]
                    )
    return pip_args


def get_project_index(project, index=None, trusted_hosts=None):
    # type: (Optional[Union[str, TSource]], Optional[List[str]], Optional[Project]) -> TSource
    from .project import SourceNotFound
    if trusted_hosts is None:
        trusted_hosts = []
    if isinstance(index, Mapping):
        return project.find_source(index.get("url"))
    try:
        source = project.find_source(index)
    except SourceNotFound:
        index_url = urllib3_util.parse_url(index)
        src_name = project.src_name_from_url(index)
        verify_ssl = index_url.host not in trusted_hosts
        source = {"url": index, "verify_ssl": verify_ssl, "name": src_name}
    return source


def get_source_list(
    project,  # type: Project
    index=None,  # type: Optional[Union[str, TSource]]
    extra_indexes=None,  # type: Optional[List[str]]
    trusted_hosts=None,  # type: Optional[List[str]]
    pypi_mirror=None,  # type: Optional[str]
):
    # type: (...) -> List[TSource]
    sources = []  # type: List[TSource]
    if index:
        sources.append(get_project_index(project, index))
    if extra_indexes:
        if isinstance(extra_indexes, str):
            extra_indexes = [extra_indexes]
        for source in extra_indexes:
            extra_src = get_project_index(project, source)
            if not sources or extra_src["url"] != sources[0]["url"]:
                sources.append(extra_src)
        else:
            for source in project.pipfile_sources:
                if not sources or source["url"] != sources[0]["url"]:
                    sources.append(source)
    if not sources:
        sources = project.pipfile_sources[:]
    if pypi_mirror:
        sources = [
            create_mirror_source(pypi_mirror) if is_pypi_url(source["url"]) else source
            for source in sources
        ]
    return sources


def get_indexes_from_requirement(req, project, index=None, extra_indexes=None, trusted_hosts=None, pypi_mirror=None):
    # type: (Requirement, Project, Optional[Text], Optional[List[Text]], Optional[List[Text]], Optional[Text]) -> Tuple[TSource, List[TSource], List[Text]]
    index_sources = []  # type: List[TSource]
    if not trusted_hosts:
        trusted_hosts = []  # type: List[Text]
    if extra_indexes is None:
        extra_indexes = []
    project_indexes = project.pipfile_sources[:]
    indexes = []
    if req.index:
        indexes.append(req.index)
    if getattr(req, "extra_indexes", None):
        if not isinstance(req.extra_indexes, list):
            indexes.append(req.extra_indexes)
        else:
            indexes.extend(req.extra_indexes)
    indexes.extend(project_indexes)
    if len(indexes) > 1:
        index, extra_indexes = indexes[0], indexes[1:]
    index_sources = get_source_list(project, index=index, extra_indexes=extra_indexes, trusted_hosts=trusted_hosts, pypi_mirror=pypi_mirror)
    if len(index_sources) > 1:
        index_source, extra_index_sources = index_sources[0], index_sources[1:]
    else:
        index_source, extra_index_sources = index_sources[0], []
    return index_source, extra_index_sources


def parse_indexes(line, strict=False):
    from argparse import ArgumentParser

    comment_re = re.compile(r"(?:^|\s+)#.*$")
    line = comment_re.sub("", line)
    parser = ArgumentParser("indexes", allow_abbrev=False)
    parser.add_argument("-i", "--index-url", dest="index")
    parser.add_argument("--extra-index-url", dest="extra_index")
    parser.add_argument("--trusted-host", dest="trusted_host")
    args, remainder = parser.parse_known_args(line.split())
    index = args.index
    extra_index = args.extra_index
    trusted_host = args.trusted_host
    if strict and sum(
        bool(arg) for arg in (index, extra_index, trusted_host, remainder)
    ) > 1:
        raise ValueError("Index arguments must be on their own lines.")
    return index, extra_index, trusted_host, remainder