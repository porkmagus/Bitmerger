"""
Bitmerger core engine: data models, similarity, merging, and utilities.

Strictly typed. No CLI or UI dependencies.
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

import tldextract
from thefuzz import fuzz  # type: ignore[import-not-found,import-untyped]

# --- Data Models ---

@dataclass
class UriEntry:
    match: Optional[str] = None
    uri: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UriEntry":
        return cls(match=d.get("match"), uri=d.get("uri", ""))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"uri": self.uri}
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
        _append_note("Merged data from duplicate entry:\n" + "\n".join(f"  \u2022 {c}" for c in conflicts))
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

def _accumulate_backfill(all_bf: Dict[str, Any], bf: Dict[str, Any]) -> None:
    """Accumulate numeric backfill counters (conflicts, fields, etc.) instead of overwriting."""
    for k, v in bf.items():
        if k in ("conflicts", "fields", "collectionIds", "passkeys"):
            all_bf[k] = all_bf.get(k, 0) + v
        else:
            all_bf[k] = v


def build_proposed_records(cluster_infos: List[ClusterInfo]) -> List[MergeRecord]:
    """Simulate merges on deep copies to build proposed records for reporting.
    
    This does NOT mutate the real items. Used for dry-run/report-only.
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


# --- HTML Report ---

def generate_html_report(
    records: List[MergeRecord],
    stats: Dict[str, Any],
    threshold: float,
    filename: str,
    output_path: Path,
) -> None:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
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


# --- Batch Rename ---

def parse_search_query(query: str) -> list[str]:
    """Split query by '+' for OR search. Each term is stripped and lowercased."""
    return [t.strip().lower() for t in query.split("+") if t.strip()]


def item_matches_terms(item: BwItem, terms: list[str]) -> bool:
    """Check if item name contains any of the search terms (case-insensitive)."""
    name_lower = (item.name or "").lower()
    return any(term in name_lower for term in terms)


def filter_items_by_name(
    items: list[BwItem],
    terms: list[str],
    target_types: set[int],
) -> list[BwItem]:
    return [i for i in items if i.type in target_types and item_matches_terms(i, terms)]


def create_rename_log(
    renamed: list[tuple[str, str, str]],
    output_path: Path,
) -> Path:
    log_data: list[Dict[str, Any]] = [{"id": rid, "old_name": old, "new_name": new} for rid, old, new in renamed]
    log_path = output_path.with_suffix(f"{output_path.suffix}.rename-log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    return log_path


# --- Vault I/O ---

def load_vault(path: Path) -> tuple[list[BwItem], dict[str, Any]]:
    """Load a Bitwarden JSON export and return (items, raw_data)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items_raw: list[Any] = data.get("items", [])
    items = [BwItem.from_dict(i) for i in items_raw]
    return items, data


def save_vault(path: Path, items: list[BwItem], original_data: dict[str, Any]) -> None:
    """Save items back to a Bitwarden JSON export file."""
    out_data = dict(original_data)
    out_data["items"] = [i.to_dict() for i in items]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)
