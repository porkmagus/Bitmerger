#!/usr/bin/env python3
"""
Bitmerger: Smart Vault Deduplicator

Reads a Bitwarden JSON export, identifies duplicates across ALL item types
(logins, cards, identities, secure notes, SSH keys), merges intelligently,
and emits a clean JSON ready for re-import.

DEFAULT BEHAVIOR: Auto-merge with keep-newest heuristic.
You can override with --review for interactive mode.
"""

import copy
import json
import re
import shutil
import string
import time
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set

import click
import tldextract
from jinja2 import Environment, FileSystemLoader, select_autoescape
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from thefuzz import fuzz  # type: ignore[import-not-found,import-untyped]

console = Console()

# --- Caches ---

# Removed per-item domain cache; normalize_domain already has @lru_cache.

# --- Data Models ---

@dataclass
class UriEntry:
    match: Optional[str] = None
    uri: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UriEntry":
        return cls(match=d.get("match"), uri=d.get("uri", ""))

    def to_dict(self) -> Dict[str, Any]:
        out = {"uri": self.uri}
        if self.match is not None:
            out["match"] = self.match
        return out


@dataclass
class LoginData:
    uris: List[UriEntry] = field(default_factory=list)  # type: ignore[type-arg]
    username: Optional[str] = None
    password: Optional[str] = None
    totp: Optional[str] = None
    fido2Credentials: Optional[List[Any]] = None

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "LoginData":
        if not d:
            return cls()
        uris_data: list[Any] = d.get("uris", [])  # type: ignore[assignment]
        return cls(
            uris=[UriEntry.from_dict(u) for u in uris_data if isinstance(u, dict)],  # type: ignore[arg-type]
            username=d.get("username"),
            password=d.get("password"),
            totp=d.get("totp"),
            fido2Credentials=d.get("fido2Credentials"),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.uris:
            out["uris"] = [u.to_dict() for u in self.uris]
        if self.username is not None:
            out["username"] = self.username
        if self.password is not None:
            out["password"] = self.password
        if self.totp is not None:
            out["totp"] = self.totp
        if self.fido2Credentials is not None:
            out["fido2Credentials"] = self.fido2Credentials
        return out


@dataclass
class SshKeyData:
    privateKey: Optional[str] = None
    publicKey: Optional[str] = None
    keyFingerprint: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "SshKeyData":
        if not d:
            return cls()
        return cls(
            privateKey=d.get("privateKey"),
            publicKey=d.get("publicKey"),
            keyFingerprint=d.get("keyFingerprint"),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "privateKey": self.privateKey or "",
            "publicKey": self.publicKey or "",
            "keyFingerprint": self.keyFingerprint or "",
        }
        return out


@dataclass
class BwItem:
    id: str
    type: int
    name: str
    notes: Optional[str] = None
    favorite: bool = False
    fields: Optional[List[Any]] = None
    reprompt: int = 0
    login: Optional[LoginData] = None
    collectionIds: Optional[List[str]] = None
    folderId: Optional[str] = None
    organizationId: Optional[str] = None
    passwordHistory: Optional[List[Any]] = None
    secureNote: Optional[Dict[str, Any]] = None
    card: Optional[Dict[str, Any]] = None
    identity: Optional[Dict[str, Any]] = None
    sshKey: Optional[SshKeyData] = None
    revisionDate: Optional[str] = None
    creationDate: Optional[str] = None
    deletedDate: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)  # type: ignore[type-arg]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BwItem":
        known = {
            "id", "type", "name", "notes", "favorite", "fields", "reprompt",
            "login", "collectionIds", "folderId", "organizationId",
            "passwordHistory", "secureNote", "card", "identity", "sshKey",
            "revisionDate", "creationDate", "deletedDate",
        }
        return cls(
            id=d.get("id", ""),
            type=d.get("type", 1),
            name=d.get("name", ""),
            notes=d.get("notes"),
            favorite=d.get("favorite", False),
            fields=d.get("fields"),
            reprompt=d.get("reprompt", 0),
            login=LoginData.from_dict(d.get("login")),
            collectionIds=d.get("collectionIds"),
            folderId=d.get("folderId"),
            organizationId=d.get("organizationId"),
            passwordHistory=d.get("passwordHistory"),
            secureNote=d.get("secureNote"),
            card=d.get("card"),
            identity=d.get("identity"),
            sshKey=SshKeyData.from_dict(d.get("sshKey")),
            revisionDate=d.get("revisionDate"),
            creationDate=d.get("creationDate"),
            deletedDate=d.get("deletedDate"),
            extra={k: v for k, v in d.items() if k not in known},
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "favorite": self.favorite,
            "reprompt": self.reprompt,
        }
        if self.notes is not None:
            out["notes"] = self.notes
        if self.fields is not None:
            out["fields"] = self.fields
        if self.login is not None and self.is_login():
            out["login"] = self.login.to_dict()
        if self.collectionIds is not None:
            out["collectionIds"] = self.collectionIds
        if self.folderId is not None:
            out["folderId"] = self.folderId
        if self.organizationId is not None:
            out["organizationId"] = self.organizationId
        if self.passwordHistory is not None:
            out["passwordHistory"] = self.passwordHistory
        if self.secureNote is not None:
            out["secureNote"] = self.secureNote
        if self.card is not None:
            out["card"] = self.card
        if self.identity is not None:
            out["identity"] = self.identity
        if self.sshKey is not None and self.is_ssh_key():
            out["sshKey"] = self.sshKey.to_dict()
        if self.revisionDate is not None:
            out["revisionDate"] = self.revisionDate
        if self.creationDate is not None:
            out["creationDate"] = self.creationDate
        if self.deletedDate is not None:
            out["deletedDate"] = self.deletedDate
        out.update(self.extra)
        return out

    def is_login(self) -> bool:
        return self.type == 1 and self.login is not None

    def is_card(self) -> bool:
        return self.type == 3 and self.card is not None

    def is_identity(self) -> bool:
        return self.type == 4 and self.identity is not None

    def is_secure_note(self) -> bool:
        return self.type == 2 and self.secureNote is not None

    def is_ssh_key(self) -> bool:
        return self.type == 5 and self.sshKey is not None

    def get_domains(self) -> Set[str]:
        if self.login:
            return {normalize_domain(u.uri) for u in self.login.uris if u.uri}
        return set()

    def get_card_fingerprint(self) -> Optional[str]:
        if not self.card:
            return None
        number = self.card.get("number", "")
        last4 = number[-4:] if len(number) >= 4 else ""
        brand = self.card.get("brand", "")
        exp = f"{self.card.get('expMonth', '')}/{self.card.get('expYear', '')}"
        return f"{brand}:{last4}:{exp}"

    def get_identity_fingerprint(self) -> Optional[str]:
        if not self.identity:
            return None
        email = (self.identity.get("email") or "").lower().strip()
        last = (self.identity.get("lastName") or "").lower().strip()
        ssn = (self.identity.get("ssn") or "").strip()
        parts = [p for p in [email, last, ssn] if p]
        return "|".join(parts) if parts else None

    def get_ssh_fingerprint(self) -> Optional[str]:
        if not self.sshKey:
            return None
        return self.sshKey.keyFingerprint or self.sshKey.publicKey

    def get_note_fingerprint(self) -> Optional[str]:
        if not self.is_secure_note():
            return None
        text = f"{self.name or ''}:{self.notes or ''}"
        return text[:200]


@dataclass
class MergeRecord:
    cluster_id: int
    primary: BwItem
    merged: List[BwItem]
    new_uris: List[str]
    backfilled: Dict[str, Any] = field(default_factory=dict)  # type: ignore[type-arg]


@dataclass
class ClusterInfo:
    """Rich cluster metadata for display/review."""
    cluster_id: int
    items: List[BwItem]
    selected_primary: int
    confidence: float  # 0.0-1.0 confidence this merge is safe
    skipped: bool = False

    def primary(self) -> BwItem:
        return self.items[self.selected_primary]


def _accumulate_backfill(all_bf: Dict[str, Any], bf: Dict[str, Any]) -> None:
    """Accumulate numeric backfill counters (conflicts, fields, etc.) instead of overwriting."""
    for k, v in bf.items():
        if k in ("conflicts", "fields", "collectionIds", "passkeys"):
            all_bf[k] = all_bf.get(k, 0) + v
        else:
            all_bf[k] = v


# --- Text Normalization ---

@lru_cache(maxsize=50000)
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text


@lru_cache(maxsize=50000)
def normalize_domain(uri: str) -> str:
    if not uri:
        return ""
    try:
        parsed = urllib.parse.urlparse(uri)
        host = parsed.hostname or uri
        extracted = tldextract.extract(host)
        domain = getattr(extracted, "top_domain_under_public_suffix", None) or getattr(extracted, "registered_domain", "")
        if domain:
            return domain.lower()
        return host.lower()
    except Exception:
        return uri.lower()


def clean_uri(uri: str) -> str:
    if not uri:
        return ""
    try:
        parsed = urllib.parse.urlparse(uri)
        return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return uri


def fuzzy_name_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return fuzz.ratio(na, nb) / 100.0  # type: ignore[operator]


# --- Type-aware similarity ---

def login_similarity(a: BwItem, b: BwItem, fast: bool = False) -> float:
    login_a = a.login
    login_b = b.login
    if login_a is None or login_b is None:
        return 0.0

    scores: list[float] = []
    weights: list[float] = []

    domains_a = a.get_domains()
    domains_b = b.get_domains()
    # Always include domain weight for logins; missing URIs = mismatch
    if domains_a or domains_b:
        overlap = domains_a & domains_b
        if overlap:
            scores.append(1.0)
        else:
            best = 0.0
            for da in domains_a:
                for db in domains_b:
                    best = max(best, fuzzy_name_similarity(da, db))
            scores.append(best)
        weights.append(0.35)

    ua = (login_a.username or "").lower().strip()
    ub = (login_b.username or "").lower().strip()
    if ua or ub:
        scores.append(1.0 if ua == ub else 0.0)
        weights.append(0.30)

    pa = login_a.password or ""
    pb = login_b.password or ""
    if pa or pb:
        scores.append(1.0 if pa == pb else 0.0)
        weights.append(0.25)

    if not fast:
        name_a = a.name or ""
        name_b = b.name or ""
        if name_a or name_b:
            scores.append(fuzzy_name_similarity(name_a, name_b))
            weights.append(0.10)

    if not scores:
        return 0.0
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def card_similarity(a: BwItem, b: BwItem) -> float:
    fp_a = a.get_card_fingerprint()
    fp_b = b.get_card_fingerprint()
    if fp_a and fp_b and fp_a == fp_b:
        return 1.0
    return fuzzy_name_similarity(a.name or "", b.name or "")


def identity_similarity(a: BwItem, b: BwItem) -> float:
    fp_a = a.get_identity_fingerprint()
    fp_b = b.get_identity_fingerprint()
    if fp_a and fp_b and fp_a == fp_b:
        return 1.0
    return fuzzy_name_similarity(a.name or "", b.name or "")


def ssh_key_similarity(a: BwItem, b: BwItem) -> float:
    fp_a = a.get_ssh_fingerprint()
    fp_b = b.get_ssh_fingerprint()
    if fp_a and fp_b and fp_a == fp_b:
        return 1.0
    return fuzzy_name_similarity(a.name or "", b.name or "")


def secure_note_similarity(a: BwItem, b: BwItem) -> float:
    fp_a = a.get_note_fingerprint()
    fp_b = b.get_note_fingerprint()
    if fp_a and fp_b and fp_a == fp_b:
        return 1.0
    return fuzzy_name_similarity(a.name or "", b.name or "")


def item_similarity(a: BwItem, b: BwItem, fast: bool = False) -> float:
    if a.type != b.type:
        return 0.0
    if a.is_login() and b.is_login():
        return login_similarity(a, b, fast=fast)
    if a.is_card() and b.is_card():
        return card_similarity(a, b)
    if a.is_identity() and b.is_identity():
        return identity_similarity(a, b)
    if a.is_ssh_key() and b.is_ssh_key():
        return ssh_key_similarity(a, b)
    if a.is_secure_note() and b.is_secure_note():
        return secure_note_similarity(a, b)
    return 0.0


# --- Confidence scoring ---

def cluster_confidence(cluster: List[BwItem]) -> float:
    """Return confidence 0.0-1.0 that this cluster is truly duplicate.
    
    High confidence = exact same credentials, domains, and names.
    Low confidence = fuzzy name match or partial data.
    """
    if len(cluster) < 2:
        return 1.0

    # Exact domain + username + password = 1.0
    first = cluster[0]
    if first.is_login() and first.login:
        domains = first.get_domains()
        user = first.login.username
        pw = first.login.password
        exact_matches = 0
        for item in cluster[1:]:
            if item.login:
                if item.login.username == user and item.login.password == pw:
                    if item.get_domains() & domains:
                        exact_matches += 1
        if exact_matches == len(cluster) - 1:
            return 1.0

    # Compute average pairwise similarity
    total = 0.0
    count = 0
    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            total += item_similarity(cluster[i], cluster[j])
            count += 1
    if count == 0:
        return 0.0
    return total / count


# --- Merging ---

def merge_items(target: BwItem, source: BwItem) -> Tuple[BwItem, Dict[str, Any]]:
    backfilled: Dict[str, Any] = {}
    conflicts: List[str] = []

    def _append_note(text: str) -> None:
        ta = (target.notes or "").strip()
        if text not in ta:
            target.notes = (ta + "\n\n" + text).strip() if ta else text

    # Generic merge
    ta = (target.notes or "").strip()
    sa = (source.notes or "").strip()
    if sa and sa != ta:
        target.notes = (ta + "\n\n" + sa).strip() if ta else sa
        backfilled["notes"] = True

    if source.favorite and not target.favorite:
        target.favorite = True
        backfilled["favorite"] = True

    if source.passwordHistory:
        if not target.passwordHistory:
            target.passwordHistory = []
        target.passwordHistory.extend(source.passwordHistory)
        backfilled["history"] = True

    if source.fields:
        if not target.fields:
            target.fields = []
        target.fields.extend(source.fields)
        backfilled["fields"] = len(source.fields)

    # Collections: union
    if source.collectionIds:
        if not target.collectionIds:
            target.collectionIds = []
        before = set(target.collectionIds)
        target.collectionIds = list(dict.fromkeys(target.collectionIds + source.collectionIds))
        added = set(target.collectionIds) - before
        if added:
            backfilled["collectionIds"] = len(added)

    # Folder: backfill if target empty
    if not target.folderId and source.folderId:
        target.folderId = source.folderId
        backfilled["folderId"] = True
    elif target.folderId and source.folderId and target.folderId != source.folderId:
        conflicts.append(f"Alternate folder: {source.folderId}")

    # Type-specific
    if target.is_login() and source.is_login():
        t_login = target.login
        s_login = source.login
        if t_login is None or s_login is None:
            return target, backfilled

        seen_uris = {clean_uri(u.uri).lower() for u in t_login.uris}
        new_uris: list[str] = []
        for u in s_login.uris:
            cu = clean_uri(u.uri).lower()
            if cu and cu not in seen_uris:
                t_login.uris.append(UriEntry(match=u.match, uri=clean_uri(u.uri)))
                seen_uris.add(cu)
                new_uris.append(clean_uri(u.uri))
        if new_uris:
            backfilled["uris"] = len(new_uris)

        # Username
        if not t_login.username and s_login.username:
            t_login.username = s_login.username
            backfilled["username"] = True
        elif t_login.username and s_login.username and t_login.username != s_login.username:
            conflicts.append(f"Alternate username: {s_login.username}")

        # Password
        if not t_login.password and s_login.password:
            t_login.password = s_login.password
            backfilled["password"] = True
        elif t_login.password and s_login.password and t_login.password != s_login.password:
            conflicts.append("Alternate password: [hidden]")

        # TOTP
        if not t_login.totp and s_login.totp:
            t_login.totp = s_login.totp
            backfilled["totp"] = True
        elif t_login.totp and s_login.totp and t_login.totp != s_login.totp:
            conflicts.append("Alternate TOTP: [hidden]")

        # Passkeys
        if s_login.fido2Credentials:
            if not t_login.fido2Credentials:
                t_login.fido2Credentials = []
            seen_ids: set[Any] = {cred.get("credentialId") for cred in t_login.fido2Credentials if isinstance(cred, dict) and cred.get("credentialId")}  # type: ignore[union-attr]
            added_count = 0
            for cred in s_login.fido2Credentials:
                cid: Any = cred.get("credentialId") if isinstance(cred, dict) else None  # type: ignore[union-attr]
                if cid and cid not in seen_ids:
                    t_login.fido2Credentials.append(cred)
                    seen_ids.add(cid)
                    added_count += 1
                elif not cid:
                    t_login.fido2Credentials.append(cred)
                    added_count += 1
            if added_count:
                backfilled["passkeys"] = added_count

    elif target.is_card() and source.is_card():
        t_card = target.card or {}
        s_card = source.card or {}
        for key in ["cardholderName", "number", "brand", "expMonth", "expYear", "code"]:
            if not t_card.get(key) and s_card.get(key):
                t_card[key] = s_card[key]
                backfilled[f"card_{key}"] = True
            elif t_card.get(key) and s_card.get(key) and t_card[key] != s_card[key]:
                conflicts.append(f"Alternate card {key}: {s_card[key]}")
        target.card = t_card

    elif target.is_identity() and source.is_identity():
        t_id = target.identity or {}
        s_id = source.identity or {}
        for key in ["title", "firstName", "middleName", "lastName", "address1", "address2",
                    "address3", "city", "state", "postalCode", "country", "company",
                    "email", "phone", "ssn", "username", "passportNumber", "licenseNumber"]:
            if not t_id.get(key) and s_id.get(key):
                t_id[key] = s_id[key]
                backfilled[f"id_{key}"] = True
            elif t_id.get(key) and s_id.get(key) and t_id[key] != s_id[key]:
                conflicts.append(f"Alternate identity {key}: {s_id[key]}")
        target.identity = t_id

    elif target.is_ssh_key() and source.is_ssh_key():
        t_ssh = target.sshKey
        s_ssh = source.sshKey
        if t_ssh is None or s_ssh is None:
            return target, backfilled
        if not t_ssh.privateKey and s_ssh.privateKey:
            t_ssh.privateKey = s_ssh.privateKey
            backfilled["ssh_private"] = True
        elif t_ssh.privateKey and s_ssh.privateKey and t_ssh.privateKey != s_ssh.privateKey:
            conflicts.append("Alternate SSH private key: [hidden]")
        if not t_ssh.publicKey and s_ssh.publicKey:
            t_ssh.publicKey = s_ssh.publicKey
            backfilled["ssh_public"] = True
        elif t_ssh.publicKey and s_ssh.publicKey and t_ssh.publicKey != s_ssh.publicKey:
            conflicts.append(f"Alternate SSH public key: {s_ssh.publicKey}")
        if not t_ssh.keyFingerprint and s_ssh.keyFingerprint:
            t_ssh.keyFingerprint = s_ssh.keyFingerprint
            backfilled["ssh_fingerprint"] = True
        elif t_ssh.keyFingerprint and s_ssh.keyFingerprint and t_ssh.keyFingerprint != s_ssh.keyFingerprint:
            conflicts.append(f"Alternate SSH fingerprint: {s_ssh.keyFingerprint}")

    if conflicts:
        _append_note("Merged data from duplicate entry:\n" + "\n".join(f"  • {c}" for c in conflicts))
        backfilled["conflicts"] = len(conflicts)

    return target, backfilled


# --- Duplicate Detection ---

def find_duplicates_by_type(items: List[BwItem], threshold: float = 0.85, fast: bool = False) -> Tuple[List[List[BwItem]], int]:
    by_type: Dict[int, List[Tuple[int, BwItem]]] = defaultdict(list)
    for idx, item in enumerate(items):
        by_type[item.type].append((idx, item))

    all_clusters: List[List[BwItem]] = []
    total_comp = 0

    for type_code, type_items in by_type.items():
        n = len(type_items)
        if n < 2:
            continue

        parent = list(range(n))
        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        # Blocking
        blocks: Dict[str, List[int]] = defaultdict(list)
        if type_code == 1:
            for i, (_, item) in enumerate(type_items):
                if item.login and item.login.username and item.login.password:
                    key = f"{item.login.username.lower().strip()}:{item.login.password}"
                    blocks[key].append(i)
                for dom in item.get_domains():
                    blocks[f"dom:{dom}"].append(i)
        elif type_code == 3:
            for i, (_, item) in enumerate(type_items):
                fp = item.get_card_fingerprint()
                if fp:
                    blocks[f"card:{fp}"].append(i)
        elif type_code == 4:
            for i, (_, item) in enumerate(type_items):
                fp = item.get_identity_fingerprint()
                if fp:
                    blocks[f"id:{fp}"].append(i)
        elif type_code == 5:
            for i, (_, item) in enumerate(type_items):
                fp = item.get_ssh_fingerprint()
                if fp:
                    blocks[f"ssh:{fp}"].append(i)
        elif type_code == 2:
            for i, (_, item) in enumerate(type_items):
                fp = item.get_note_fingerprint()
                if fp:
                    blocks[f"note:{fp}"].append(i)

        for block_key, block in blocks.items():
            if len(block) < 2:
                continue
            # Safety cap: credential blocks >50 are almost certainly password reuse (not duplicates)
            # Domain blocks can legitimately be large (e.g., google.com), so cap them higher.
            if len(block) > 50 and not block_key.startswith("dom:"):
                continue
            if len(block) > 200:
                continue
            for i in range(len(block)):
                for j in range(i + 1, len(block)):
                    total_comp += 1
                    if item_similarity(type_items[block[i]][1], type_items[block[j]][1], fast=fast) >= threshold:
                        union(block[i], block[j])

        # Fallback orphans
        processed: set[int] = set()
        for block in blocks.values():
            processed.update(block)
        orphans = [i for i in range(n) if i not in processed]
        if len(orphans) > 500:
            orphans = []
        for i in range(len(orphans)):
            for j in range(i + 1, len(orphans)):
                total_comp += 1
                if item_similarity(type_items[orphans[i]][1], type_items[orphans[j]][1], fast=fast) >= threshold:
                    union(orphans[i], orphans[j])

        groups: Dict[int, List[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)

        for idxs in groups.values():
            if len(idxs) > 1:
                cluster = [type_items[i][1] for i in idxs]
                # Safety cap: clusters >100 are pathological (almost certainly false positives)
                if len(cluster) <= 100:
                    all_clusters.append(cluster)

    return all_clusters, total_comp


# --- Primary Selection ---

def pick_primary(cluster: List[BwItem]) -> int:
    """Pick the best primary item index using a multi-factor heuristic."""
    def score(c: BwItem) -> tuple[int, ...]:
        if c.is_login() and c.login:
            return (
                len(c.login.uris),
                1 if c.folderId else 0,
                1 if c.login.fido2Credentials else 0,
                1 if c.login.totp else 0,
                1 if c.notes else 0,
                1 if c.passwordHistory else 0,
                len(c.fields) if c.fields else 0,
                -len(c.name),
            )
        elif c.is_card() and c.card:
            return (1 if c.card.get("number") else 0, 1 if c.notes else 0, -len(c.name))
        elif c.is_identity() and c.identity:
            return (1 if c.identity.get("email") else 0, 1 if c.notes else 0, -len(c.name))
        elif c.is_ssh_key() and c.sshKey:
            return (1 if c.sshKey.keyFingerprint else 0, 1 if c.sshKey.publicKey else 0, -len(c.name))
        elif c.is_secure_note():
            return (len(c.notes or ""), -len(c.name))
        return (-len(c.name),)
    return max(range(len(cluster)), key=lambda i: score(cluster[i]))


# --- Report ---

def show_duplicate_report(clusters: List[List[BwItem]], max_display: int = 50) -> None:
    display = clusters[:max_display]
    type_names = {1: "Login", 2: "Note", 3: "Card", 4: "Identity", 5: "SSH"}
    table = Table(title=f"Duplicate Clusters (showing {len(display)} of {len(clusters)})", show_lines=True)
    table.add_column("Cluster", style="cyan", no_wrap=True)
    table.add_column("Type", style="yellow")
    table.add_column("Count")
    table.add_column("Names")
    table.add_column("Confidence", style="green")
    table.add_column("Key", style="dim")

    for idx, cluster in enumerate(display, 1):
        first = cluster[0]
        tname = type_names.get(first.type, "Other")
        names = [c.name for c in cluster]
        conf = cluster_confidence(cluster)
        conf_style = "green" if conf >= 0.95 else "yellow" if conf >= 0.85 else "red"

        key = ""
        if first.is_login():
            key = (first.login.username or "") if first.login else ""
        elif first.is_card():
            key = first.get_card_fingerprint() or ""
        elif first.is_identity():
            key = first.identity.get("email", "") if first.identity else ""
        elif first.is_ssh_key():
            key = (first.sshKey.keyFingerprint or "") if first.sshKey else ""

        table.add_row(
            f"#{idx}", tname, str(len(cluster)), "\n".join(names),
            f"[{conf_style}]{conf:.0%}[/{conf_style}]", key
        )
    console.print(table)
    if len(clusters) > max_display:
        console.print(f"[dim]... and {len(clusters) - max_display} more clusters")


# --- HTML Report ---

def generate_html_report(
    records: List[MergeRecord],
    stats: Dict[str, Any],
    threshold: float,
    filename: str,
    output_path: Path,
) -> None:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.jinja2")

    def mask(pw: Optional[str]) -> str:
        return "*" * len(pw) if pw else "(none)"

    def fmt_item(item: BwItem) -> Dict[str, Any]:
        domain = ""
        uris: list[str] = []
        username = ""
        password = ""
        ssh_fp = ""
        if item.login:
            for u in item.login.uris:
                uris.append(clean_uri(u.uri))
                if not domain:
                    domain = normalize_domain(u.uri)
            username = item.login.username or ""
            password = item.login.password or ""
        if item.sshKey:
            ssh_fp = item.sshKey.keyFingerprint or ""
        return {
            "id": item.id,
            "name": item.name,
            "username": username,
            "password_mask": mask(password),
            "domain": domain,
            "uris": uris,
            "notes": item.notes or "",
            "ssh_fingerprint": ssh_fp,
            "type": item.type,
        }

    clusters: list[Dict[str, Any]] = []
    for idx, rec in enumerate(records, 1):
        primary = rec.primary
        p_domain = ""
        p_uris: list[str] = []
        p_username = ""
        p_password = ""
        p_ssh_fp = ""
        if primary.login:
            for u in primary.login.uris:
                p_uris.append(clean_uri(u.uri))
                if not p_domain:
                    p_domain = normalize_domain(u.uri)
            p_username = primary.login.username or ""
            p_password = primary.login.password or ""
        if primary.sshKey:
            p_ssh_fp = primary.sshKey.keyFingerprint or ""

        clusters.append({
            "id": idx,
            "primary_id": primary.id,
            "primary_name": primary.name,
            "primary_username": p_username,
            "primary_password_mask": mask(p_password),
            "primary_domain": p_domain,
            "primary_uris": p_uris,
            "primary_notes": primary.notes or "",
            "primary_ssh_fp": p_ssh_fp,
            "primary_type": primary.type,
            "members": [fmt_item(i) for i in rec.merged],
            "new_uris": rec.new_uris,
            "backfilled": rec.backfilled,
        })

    html = template.render(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        threshold=threshold,
        filename=filename,
        stats=stats,
        clusters=clusters,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    console.print(f"[bold green]HTML report written to[/] {output_path}")


# --- Safety / Backup ---

def create_backup(original_path: Path) -> Path:
    """Create a timestamped backup of the original file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = original_path.with_suffix(f".original.{ts}.json")
    shutil.copy2(original_path, backup)
    return backup


def create_merge_log(records: List[MergeRecord], output_path: Path) -> Path:
    """Create a JSON log of all merges so the user can audit/rollback."""
    log_data: list[Dict[str, Any]] = []
    for rec in records:
        log_data.append({
            "cluster_id": rec.cluster_id,
            "primary_id": rec.primary.id,
            "primary_name": rec.primary.name,
            "merged_ids": [c.id for c in rec.merged if c.id != rec.primary.id],
            "merged_names": [c.name for c in rec.merged if c.id != rec.primary.id],
            "backfilled": rec.backfilled,
        })
    log_path = output_path.with_suffix(f"{output_path.suffix}.merge-log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    return log_path


# --- Proposed Records (for Report Only / Dry Run) ---

def _build_proposed_records(cluster_infos: List[ClusterInfo]) -> List[MergeRecord]:
    """Simulate merges on deep copies to build proposed records for reporting.
    
    This does NOT mutate the real items. Used for --report-only and --dry-run.
    """
    records: List[MergeRecord] = []
    for ci in cluster_infos:
        if ci.skipped:
            continue
        primary = copy.deepcopy(ci.items[ci.selected_primary])
        all_new_uris: List[str] = []
        all_backfilled: Dict[str, Any] = {}
        for i, c in enumerate(ci.items):
            if i == ci.selected_primary:
                continue
            primary, backfilled = merge_items(primary, c)
            for k, v in backfilled.items():
                if k == "uris":
                    if c.login:
                        for u in c.login.uris:
                            cu = clean_uri(u.uri)
                            if cu:
                                all_new_uris.append(cu)
                else:
                    _accumulate_backfill(all_backfilled, {k: v})
        seen: set[str] = {clean_uri(u.uri).lower() for u in primary.login.uris} if primary.login else set()
        unique_new: list[str] = []
        for u_str in all_new_uris:
            cu_cleaned: str = clean_uri(u_str).lower()
            if cu_cleaned not in seen:
                unique_new.append(u_str)
                seen.add(cu_cleaned)
        records.append(MergeRecord(
            cluster_id=ci.cluster_id + 1,
            primary=primary,
            merged=ci.items,
            new_uris=unique_new,
            backfilled=all_backfilled,
        ))
    return records


# --- Main CLI ---

@click.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output JSON path.")
@click.option("-t", "--threshold", type=float, default=0.85, show_default=True, help="Similarity threshold.")
@click.option("--review", is_flag=True, help="Interactive review mode (prompt for each cluster).")
@click.option("--dry-run", is_flag=True, help="Preview + generate report without writing output.")
@click.option("--report-only", is_flag=True, help="Analyze + generate report only. No merge, no output.")
@click.option("--fast", is_flag=True, help="Skip expensive fuzzy matching for speed.")
@click.option("--types", type=str, default="1,2,3,4,5", help="Comma-separated item types to deduplicate.")
@click.option("--no-backup", is_flag=True, help="Skip creating a backup of the original file.")
@click.option("--confidence", type=float, default=None, help="Only auto-merge clusters above this confidence (0.0-1.0).")
def main(
    input_file: str,
    output: Optional[str],
    threshold: float,
    review: bool,
    dry_run: bool,
    report_only: bool,
    fast: bool,
    types: str,
    no_backup: bool,
    confidence: Optional[float],
):
    input_path = Path(input_file)
    output_path = Path(output) if output else input_path.with_suffix(".dedup.json")
    report_path = input_path.with_suffix(".report.html")
    target_types = set(int(t.strip()) for t in types.split(",") if t.strip().isdigit())

    t0 = time.time()
    console.print(f"[bold green]Loading[/] {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items_raw: list[Any] = data.get("items", [])  # type: ignore[assignment]
    all_items: list[BwItem] = [BwItem.from_dict(i) for i in items_raw]

    type_counts: defaultdict[int, int] = defaultdict(int)
    for item in all_items:
        type_counts[item.type] += 1
    type_names = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH Keys"}
    counts_str = ", ".join(f"{type_names.get(t, f'Type{t}')}: {c}" for t, c in sorted(type_counts.items()))
    console.print(f"[bold]Total items:[/] {len(all_items)} [dim]({counts_str})")
    console.print(f"[bold]Deduplicating types:[/] {sorted(target_types)}")
    console.print(f"[dim](loaded in {time.time() - t0:.2f}s)")

    dedup_items: list[BwItem] = [i for i in all_items if i.type in target_types]
    pass_through: list[BwItem] = [i for i in all_items if i.type not in target_types]

    if not dedup_items:
        console.print("[yellow]No items of target types found. Nothing to do.")
        return

    clusters, total_comp = find_duplicates_by_type(dedup_items, threshold=threshold, fast=fast)
    console.print(f"[dim]Total similarity comparisons: {total_comp:,}")
    console.print(f"[bold magenta]Found {len(clusters)} duplicate clusters[/] (threshold={threshold})")

    if not clusters:
        console.print("[green]No duplicates found. Nothing to do.")
        return

    show_duplicate_report(clusters)

    # Build cluster info
    cluster_infos: list[ClusterInfo] = []
    for idx, cluster in enumerate(clusters):
        best_idx = pick_primary(cluster)
        conf = cluster_confidence(cluster)
        cluster_infos.append(ClusterInfo(
            cluster_id=idx,
            items=cluster,
            selected_primary=best_idx,
            confidence=conf,
        ))

    # Confidence filtering
    high_conf = [ci for ci in cluster_infos if ci.confidence >= 0.95]
    med_conf = [ci for ci in cluster_infos if 0.85 <= ci.confidence < 0.95]
    low_conf = [ci for ci in cluster_infos if ci.confidence < 0.85]

    console.print("\n[bold]Confidence Distribution[/]")
    console.print(f"  [green]High (>=95%):[/] {len(high_conf)} clusters — auto-merge safe")
    console.print(f"  [yellow]Medium (85-95%):[/] {len(med_conf)} clusters — review recommended")
    console.print(f"  [red]Low (<85%):[/] {len(low_conf)} clusters — review strongly recommended")

    # Interactive review mode
    if review:
        for ci in cluster_infos:
            primary = ci.primary()
            console.print(f"\n[bold]Cluster #{ci.cluster_id + 1}[/] [dim](confidence: {ci.confidence:.0%})[/]")
            for i, item in enumerate(ci.items):
                marker = "🟢" if i == ci.selected_primary else "🔴"
                console.print(f"  {marker} {item.name}")
            if ci.confidence >= 0.95:
                default = "y"
            else:
                default = "n"
            choice = Prompt.ask(
                f"Merge into [bold]{primary.name}[/]?",
                default=default,
                choices=["y", "n", "s"],
                show_choices=True,
            )
            if choice == "y":
                ci.skipped = False
            elif choice == "s":
                ci.skipped = True
            else:
                # Pick different primary
                choices = [f"{i+1}. {c.name}" for i, c in enumerate(ci.items)]
                for ch in choices:
                    console.print(f"    {ch}")
                new_idx = Prompt.ask(
                    "Pick primary",
                    default="1",
                    choices=[str(i+1) for i in range(len(ci.items))]
                )
                ci.selected_primary = int(new_idx) - 1
                ci.skipped = False

    # Apply confidence filter if specified
    if confidence is not None:
        approved: list[ClusterInfo] = [ci for ci in cluster_infos if ci.confidence >= confidence and not ci.skipped]
        skipped: list[ClusterInfo] = [ci for ci in cluster_infos if ci.confidence < confidence or ci.skipped]
        for ci in skipped:
            ci.skipped = True
        console.print(f"\n[bold]Confidence Filter Applied:[/] {confidence:.0%}")
        console.print(f"  Approved: {len(approved)} clusters")
        console.print(f"  Skipped: {len(skipped)} clusters")

    # Determine mode
    if report_only or dry_run:
        # Simulate merges for reporting without mutating real items
        proposed_records: List[MergeRecord] = _build_proposed_records(cluster_infos)
        report_stats: Dict[str, int] = {
            "original": len(all_items),
            "final": len(all_items) - len(proposed_records),
            "merged": len(proposed_records),
            "clusters": len(clusters),
        }
        console.print("\n[bold]Summary[/]")
        console.print(f"  Original items: {report_stats['original']}")
        console.print(f"  Would merge: {report_stats['merged']} clusters")
        console.print(f"  Total time: {time.time() - t0:.2f}s")
        if dry_run:
            console.print("\n[yellow]Dry run — no files written[/]")
        else:
            console.print("\n[yellow]Report only — no output or backup written[/]")
        # Always generate report
        generate_html_report(
            records=proposed_records,
            stats=report_stats,
            threshold=threshold,
            filename=input_path.name,
            output_path=report_path,
        )
        return

    # Build merge plan (real merge)
    merged_away_ids: set[str] = set()
    merge_records: List[MergeRecord] = []

    for ci in cluster_infos:
        if ci.skipped:
            continue
        primary = ci.items[ci.selected_primary]
        all_new_uris: List[str] = []
        all_backfilled: Dict[str, Any] = {}

        for i, c in enumerate(ci.items):
            if i != ci.selected_primary:
                primary, backfilled = merge_items(primary, c)
                merged_away_ids.add(c.id)
                for k, v in backfilled.items():
                    if k == "uris":
                        if c.login:
                            all_new_uris.extend([clean_uri(u.uri) for u in c.login.uris])
                    else:
                        _accumulate_backfill(all_backfilled, {k: v})

        seen: set[str] = {clean_uri(u.uri).lower() for u in primary.login.uris} if primary.login else set()
        unique_new: list[str] = []
        for u_str in all_new_uris:
            cu_cleaned: str = clean_uri(u_str).lower()
            if cu_cleaned not in seen:
                unique_new.append(u_str)
                seen.add(cu_cleaned)

        merge_records.append(
            MergeRecord(
                cluster_id=ci.cluster_id + 1,
                primary=primary,
                merged=ci.items,
                new_uris=unique_new,
                backfilled=all_backfilled,
            )
        )

    kept: list[BwItem] = [i for i in dedup_items if i.id not in merged_away_ids]
    final_items: list[BwItem] = kept + pass_through

    out_data: Dict[str, Any] = dict(data)
    out_data["items"] = [i.to_dict() for i in final_items]

    final_stats: Dict[str, int] = {
        "original": len(all_items),
        "final": len(final_items),
        "merged": len(merged_away_ids),
        "clusters": len(clusters),
    }

    console.print("\n[bold]Summary[/]")
    console.print(f"  Original items: {final_stats['original']}")
    console.print(f"  Merged away: {final_stats['merged']}")
    console.print(f"  Final items: {final_stats['final']}")
    console.print(f"  Total time: {time.time() - t0:.2f}s")

    # Backup
    if not no_backup:
        backup = create_backup(input_path)
        console.print(f"\n[dim]Backup created: {backup}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)
    console.print(f"\n[bold green]Wrote clean export to[/] {output_path}")

    # Merge log
    if merge_records:
        log_path = create_merge_log(merge_records, output_path)
        console.print(f"[dim]Merge log: {log_path}")

    # HTML report (always generated)
    generate_html_report(
        records=merge_records,
        stats=final_stats,
        threshold=threshold,
        filename=input_path.name,
        output_path=report_path,
    )

    # Final banner
    console.print(Panel(
        Text.assemble(
            ("Cleaned ", "bold white"),
            (f"{final_stats['merged']}", "bold green"),
            (" duplicates from ", "bold white"),
            (f"{final_stats['original']}", "bold blue"),
            (" items.", "bold white"),
            ("\n", ""),
            ("Import back into Bitwarden via: Tools → Import Data → Bitwarden (json)", "dim"),
        ),
        title="🔐 Bitmerger Complete",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
