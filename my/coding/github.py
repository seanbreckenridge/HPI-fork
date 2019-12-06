from typing import Dict, List, Union, Any, NamedTuple, Tuple, Optional, Iterator, TypeVar
from datetime import datetime
import json
from pathlib import Path
import logging

import pytz

from ..common import get_files

from my_configuration import paths
import my_configuration.repos.ghexport.model as ghexport


def get_logger():
    return logging.getLogger('my.github') # TODO __package__???


class Event(NamedTuple):
    dt: datetime
    summary: str
    eid: str
    link: Optional[str]
    body: Optional[str]=None


T = TypeVar('T')
Res = Union[T, Exception]

# TODO split further, title too
def _get_summary(e) -> Tuple[str, Optional[str]]:
    tp = e['type']
    pl = e['payload']
    rname = e['repo']['name']
    if tp == 'ForkEvent':
        url = e['payload']['forkee']['html_url']
        return f"forked {rname}", url
    elif tp == 'PushEvent':
        return f"pushed to {rname}", None
    elif tp == 'WatchEvent':
        return f"watching {rname}", None
    elif tp == 'CreateEvent':
        return f"created {rname}", None
    elif tp == 'PullRequestEvent':
        pr = pl['pull_request']
        action = pl['action']
        link = pr['html_url']
        title = pr['title']
        return f"{action} PR {title}", link
    elif tp == "IssuesEvent":
        action = pl['action']
        iss = pl['issue']
        link = iss['html_url']
        title = iss['title']
        return f"{action} issue {title}", link
    elif tp == "IssueCommentEvent":
        com = pl['comment']
        link = com['html_url']
        iss = pl['issue']
        title = iss['title']
        return f"commented on issue {title}", link
    elif tp == "ReleaseEvent":
        action = pl['action']
        rel = pl['release']
        tag = rel['tag_name']
        link = rel['html_url']
        return f"{action} {rname} [{tag}]", link
    elif tp in (
            "DeleteEvent",
            "PublicEvent",
    ):
        return tp, None # TODO ???
    else:
        return tp, None


def get_model():
    sources = get_files(paths.github.export_dir, glob='*.json')
    model = ghexport.Model(sources)
    return model


def _parse_dt(s: str) -> datetime:
    # TODO isoformat?
    return pytz.utc.localize(datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ'))


# TODO typing.TypedDict could be handy here..
def _parse_common(d: Dict) -> Dict:
    url = d['url']
    body = d.get('body')
    return {
        'dt'  : _parse_dt(d['created_at']),
        'link': url,
        'body': body,
    }


def _parse_repository(d: Dict) -> Event:
    name = d['name']
    return Event(
        **_parse_common(d),
        summary='created ' + name,
        eid='created_' + name, # TODO ??
    )

def _parse_issue_comment(d: Dict) -> Event:
    url = d['url']
    return Event(
        **_parse_common(d),
        summary=f'commented on issue {url}',
        eid='issue_comment_' + url,
    )


#  Event(dt=datetime.datetime(2019, 10, 15, 22, 50, 57, tzinfo=<UTC>), summary='opened issue Make seting up easier', eid='10638242494', link='https://github.com/karlicoss/my/issues/1', body=None),
def _parse_issue(d: Dict) -> Event:
    url = d['url']
    title = d['title']
    return Event(
        **_parse_common(d),
        summary=f'opened issue {title}',
        eid='issue_comment_' + url,
    )


def _parse_event(d: Dict) -> Event:
    summary, link = _get_summary(d)
    body = d.get('payload', {}).get('comment', {}).get('body')
    return Event(
        dt=_parse_dt(d['created_at']),
        summary=summary,
        link=link,
        eid=d['id'],
        body=body,
    )


def iter_gdpr_events() -> Iterator[Res[Event]]:
    """
    Parses events from GDPR export (https://github.com/settings/admin)
    """
    files = list(sorted(paths.github.gdpr_dir.glob('*.json')))
    handler_map = {
        'schema'       : None,
        'issue_events_': None, # eh, doesn't seem to have any useful bodies
        'attachments_' : None, # not sure if useful
        'repositories_'  : _parse_repository,
        'issue_comments_': _parse_issue_comment,
        'issues_'        : _parse_issue,
    }
    for f in files:
        handler: Any
        for prefix, h in handler_map.items():
            if not f.name.startswith(prefix):
                continue
            handler = h
            break
        else:
            yield RuntimeError(f'Unhandled file: {f}')
            continue

        if handler is None:
            # ignored
            continue

        j = json.loads(f.read_text())
        for r in j:
            try:
                yield handler(r)
            except Exception as e:
                yield e


def iter_events():
    model = get_model()
    for d in model.events():
        yield _parse_event(d)


# TODO load events from GDPR export?
def get_events():
    return sorted(iter_events(), key=lambda e: e.dt)

# TODO mm. ok, not much point in deserializing as github.Event as it's basically a fancy dict wrapper?
# from github.Event import Event as GEvent # type: ignore
# # see https://github.com/PyGithub/PyGithub/blob/master/github/GithubObject.py::GithubObject.__init__
# e = GEvent(None, None, raw_event, True)


def test():
    events = get_events()
    assert len(events) > 100
    for e in events:
        print(e)
