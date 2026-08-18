"""Format adapters and safe cross-vault merge support.

This module is deliberately UI-free.  It normalizes Bitwarden JSON and 1Password
1PUX exports into Bitmerger's existing ``BwItem`` working model, runs the same
strict deduplication engine, and writes a fresh import/export artifact for each
format.  Plaintext vault files are never uploaded or logged.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from .core import (
    BwItem,
    ClusterInfo,
    LoginData,
    UriEntry,
    build_proposed_records,
    cluster_confidence,
    find_duplicates_by_type,
    merge_items,
    pick_primary,
)

VaultFormat = Literal["bitwarden", "1password", "1password_csv"]

# These are the category UUIDs used by the 1PUX schema for the four categories
# that map directly to Bitwarden's supported item types.  Unknown 1Password
# categories are retained as secure notes rather than silently discarded.
_ONEPASSWORD_CATEGORY_TO_BW = {"001": 1, "002": 3, "003": 2, "004": 4}
_BW_CATEGORY_TO_ONEPASSWORD = {1: "001", 2: "003", 3: "002", 4: "004"}
_OUTPUT_FILENAMES = ("bitmerger-merged.bitwarden.json", "bitmerger-merged.1password.1pux", "bitmerger-merged.report.json")
_MAX_1PUX_MEMBERS = 10_000
_MAX_1PUX_TOTAL_BYTES = 250 * 1024 * 1024
_MAX_1PUX_EXPORT_DATA_BYTES = 100 * 1024 * 1024
_MAX_1PUX_COMPRESSION_RATIO = 200



class VaultFormatError(ValueError):
    """Raised when an input is not a supported, unencrypted vault export."""


@dataclass
class VaultDocument:
    """A normalized plaintext vault plus enough metadata to write its format."""

    format: VaultFormat
    items: list[BwItem]
    raw_data: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class DualMergeResult:
    """Outputs and auditable merge metadata from a dual-vault run."""

    bitwarden_output: Path
    onepassword_output: Path
    report_output: Path
    input_count: int
    output_count: int
    merged_count: int
    cluster_count: int
    warnings: list[str] = field(default_factory=list)


def expected_merge_outputs(output_dir: Path) -> tuple[Path, Path, Path]:
    """Return the fixed artifact names produced by a dual-vault merge."""
    directory = Path(output_dir)
    return (
        directory / _OUTPUT_FILENAMES[0],
        directory / _OUTPUT_FILENAMES[1],
        directory / _OUTPUT_FILENAMES[2],
    )


def _validate_1pux_archive(archive: zipfile.ZipFile) -> None:
    """Reject malformed or bomb-scale 1PUX archives before reading payloads."""
    infos = archive.infolist()
    if len(infos) > _MAX_1PUX_MEMBERS:
        raise VaultFormatError("1Password export has too many archive members")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise VaultFormatError("1Password export contains duplicate archive members")
    total_size = 0
    for info in infos:
        if info.filename.startswith(("/", "\\")) or ".." in Path(info.filename).parts:
            raise VaultFormatError("1Password export contains an unsafe archive path")
        total_size += info.file_size
        if info.compress_size and info.file_size / info.compress_size > _MAX_1PUX_COMPRESSION_RATIO:
            raise VaultFormatError("1Password export has a suspicious compression ratio")
    if total_size > _MAX_1PUX_TOTAL_BYTES:
        raise VaultFormatError("1Password export is too large to process safely")
    try:
        export_data = archive.getinfo("export.data")
    except KeyError as exc:
        raise VaultFormatError("1Password export is missing export.data") from exc
    if export_data.file_size > _MAX_1PUX_EXPORT_DATA_BYTES:
        raise VaultFormatError("1Password export data is too large to process safely")


def detect_vault_format(path: Path) -> VaultFormat:
    """Detect a Bitwarden JSON export or a 1Password 1PUX archive by content."""
    path = Path(path)
    if not path.is_file():
        raise VaultFormatError(f"Vault file does not exist: {path}")
    if path.suffix.lower() == ".csv":
        return "1password_csv"
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            _validate_1pux_archive(archive)
            if "export.data" in archive.namelist() and "export.attributes" in archive.namelist():
                return "1password"
        raise VaultFormatError("Unsupported ZIP vault: expected a 1Password .1pux export")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VaultFormatError("Unsupported vault: expected Bitwarden JSON or 1Password .1pux") from exc
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return "bitwarden"
    raise VaultFormatError("Unsupported JSON vault: expected a Bitwarden export with an 'items' list")


def load_document(path: Path) -> VaultDocument:
    """Load one of the supported unencrypted export formats."""
    format_name = detect_vault_format(path)
    if format_name == "bitwarden":
        return _load_bitwarden(path)
    if format_name == "1password_csv":
        return _load_1password_csv(path)
    return _load_1password(path)


def _load_bitwarden(path: Path) -> VaultDocument:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("encrypted") is True:
        raise VaultFormatError("This Bitwarden vault is encrypted; export decrypted JSON first.")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise VaultFormatError("Invalid Bitwarden export: 'items' must be a list")
    items: list[BwItem] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped Bitwarden item {index}: item was not an object")
            continue
        raw_copy = copy.deepcopy(raw)
        raw_copy.setdefault("id", str(uuid.uuid4()))
        try:
            items.append(BwItem.from_dict(raw_copy))
        except (TypeError, ValueError) as exc:
            warnings.append(f"Skipped Bitwarden item {index}: {exc}")
    return VaultDocument("bitwarden", items, data, Path(path), warnings)


def _as_text(value: Any) -> str:
    """Extract a portable text representation from a 1PUX field value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("concealed", "string", "reference"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _onepassword_fields(raw_item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_details = raw_item.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    raw_sections = details.get("sections")
    sections: list[Any] = raw_sections if isinstance(raw_sections, list) else []
    fields: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_title = str(section.get("title") or "").strip()
        for field in section.get("fields", []):
            if not isinstance(field, dict):
                continue
            title = str(field.get("title") or field.get("id") or "Untitled field").strip()
            if section_title:
                title = f"{section_title}: {title}"
            fields.append({"name": title, "value": _as_text(field.get("value")), "type": 1 if isinstance(field.get("value"), dict) and "concealed" in field["value"] else 0})
    return fields


def _onepassword_to_item(raw_item: dict[str, Any], vault_name: str, fallback_index: int, source_scope: str) -> tuple[BwItem, list[str]]:
    """Map one 1PUX item into a loss-aware Bitwarden working item."""
    warnings: list[str] = []
    raw_overview = raw_item.get("overview")
    overview: dict[str, Any] = raw_overview if isinstance(raw_overview, dict) else {}
    raw_details = raw_item.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    category = str(raw_item.get("categoryUuid") or "")
    bw_type = _ONEPASSWORD_CATEGORY_TO_BW.get(category, 2)
    title = str(overview.get("title") or f"Untitled 1Password item {fallback_index}")
    item_id = str(raw_item.get("uuid") or uuid.uuid4())
    urls = overview.get("urls") if isinstance(overview.get("urls"), list) else []
    uris = [UriEntry(uri=str(entry.get("url") or "")) for entry in urls if isinstance(entry, dict) and entry.get("url")]
    if not uris and overview.get("url"):
        uris.append(UriEntry(uri=str(overview["url"])))

    login_fields = details.get("loginFields") if isinstance(details.get("loginFields"), list) else []
    username = password = ""
    for field in login_fields:
        if not isinstance(field, dict):
            continue
        designation = field.get("designation")
        value = _as_text(field.get("value"))
        if designation == "username":
            username = value
        elif designation == "password":
            password = value
    notes = details.get("notesPlain") if isinstance(details.get("notesPlain"), str) else None
    tags = overview.get("tags") if isinstance(overview.get("tags"), list) else []
    custom_fields = _onepassword_fields(raw_item)
    if tags:
        custom_fields.extend({"name": "1Password tag", "value": str(tag), "type": 0} for tag in tags)
    if category not in _ONEPASSWORD_CATEGORY_TO_BW:
        warnings.append(f"1Password item '{title}' uses unsupported category {category or 'unknown'}; retained as a secure note.")
        custom_fields.append({"name": "1Password category", "value": category or "unknown", "type": 0})

    item = BwItem(
        id=f"1p-{source_scope}-{item_id}",
        type=bw_type,
        name=title,
        notes=notes,
        favorite=bool(raw_item.get("favIndex", 0)),
        fields=custom_fields or None,
        login=LoginData(uris=uris, username=username or None, password=password or None) if bw_type == 1 else None,
        secureNote={"type": 0} if bw_type == 2 else None,
        card=_onepassword_card(details) if bw_type == 3 else None,
        identity=_onepassword_identity(details) if bw_type == 4 else None,
        extra={"_bitmerger_source": "1password", "_bitmerger_vault": vault_name},
    )
    return item, warnings


def _fields_by_title(details: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in _onepassword_fields({"details": details}):
        values[field["name"].split(": ")[-1].lower()] = str(field["value"])
    return values


def _onepassword_card(details: dict[str, Any]) -> dict[str, Any]:
    fields = _fields_by_title(details)
    return {
        "cardholderName": fields.get("cardholder") or fields.get("cardholder name") or "",
        "number": fields.get("number") or fields.get("ccnum") or "",
        "brand": fields.get("type") or "",
        "expMonth": fields.get("expiry month") or fields.get("month") or "",
        "expYear": fields.get("expiry year") or fields.get("year") or "",
        "code": fields.get("cvv") or fields.get("verification number") or "",
    }


def _onepassword_identity(details: dict[str, Any]) -> dict[str, Any]:
    fields = _fields_by_title(details)
    return {
        "firstName": fields.get("first name") or "",
        "lastName": fields.get("last name") or "",
        "email": fields.get("email") or "",
        "phone": fields.get("phone") or "",
        "address1": fields.get("address") or "",
        "city": fields.get("city") or "",
        "state": fields.get("state") or "",
        "postalCode": fields.get("zip") or fields.get("postal code") or "",
        "country": fields.get("country") or "",
    }


def _csv_bool(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _load_1password(path: Path) -> VaultDocument:
    warnings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        _validate_1pux_archive(archive)
        try:
            data = json.loads(archive.read("export.data").decode("utf-8"))
            attributes = json.loads(archive.read("export.attributes").decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultFormatError("Invalid 1Password .1pux archive") from exc
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
            raise VaultFormatError("Invalid 1Password .1pux export: 'accounts' must be a list")
        items: list[BwItem] = []
        index = 0
        for account_index, account in enumerate(data["accounts"]):
            if not isinstance(account, dict):
                continue
            raw_vaults = account.get("vaults")
            vaults: list[Any] = raw_vaults if isinstance(raw_vaults, list) else []
            for vault_index, vault in enumerate(vaults):
                if not isinstance(vault, dict):
                    continue
                raw_attrs = vault.get("attrs")
                attrs: dict[str, Any] = raw_attrs if isinstance(raw_attrs, dict) else {}
                vault_name = str(attrs.get("name") or "1Password")
                account_id = str(account.get("uuid") or f"account-{account_index}")
                vault_id = str(vault.get("uuid") or f"vault-{vault_index}")
                for raw_item in vault.get("items", []):
                    index += 1
                    if not isinstance(raw_item, dict):
                        warnings.append(f"Skipped 1Password item {index}: item was not an object")
                        continue
                    converted, item_warnings = _onepassword_to_item(raw_item, vault_name, index, f"{account_id}-{vault_id}")
                    items.append(converted)
                    warnings.extend(item_warnings)
        attachment_count = len([name for name in archive.namelist() if name.startswith("files/") and not name.endswith("/")])
        if attachment_count:
            warnings.append(f"The source 1Password export has {attachment_count} attachment(s). They are not converted into Bitwarden JSON.")
    raw_data = {"onepassword": data, "attributes": attributes}
    return VaultDocument("1password", items, raw_data, Path(path), warnings)


def _load_1password_csv(path: Path) -> VaultDocument:
    """Load the login-only CSV produced by 1Password 8."""
    warnings: list[str] = []
    items: list[BwItem] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        normalized = {column.casefold(): column for column in columns}
        title_column = normalized.get("title")
        if not title_column:
            raise VaultFormatError("Invalid 1Password CSV: missing Title column")
        for index, row in enumerate(reader, start=1):
            title = (row.get(title_column) or "").strip()
            if not title:
                warnings.append(f"Skipped CSV row {index}: missing title")
                continue
            value = lambda name: (row.get(normalized.get(name, "")) or "").strip()
            uri = value("url") or value("website")
            username = value("username")
            password = value("password")
            otp = value("otpauth") or value("one-time password")
            fields: list[dict[str, Any]] = []
            if _csv_bool(value("archived")):
                fields.append({"name": "1Password state", "value": "archived", "type": 0})
            tags = value("tags")
            for tag in (part.strip() for part in tags.split(";") if part.strip()):
                fields.append({"name": "1Password tag", "value": tag, "type": 0})
            login = LoginData(uris=[UriEntry(uri=uri)] if uri else [], username=username or None, password=password or None)
            if otp:
                if otp.casefold().startswith("otpauth://totp/"):
                    login.totp = otp
                else:
                    fields.append({"name": "1Password CSV OTPAuth (unverified)", "value": otp, "type": 1})
                    warnings.append(f"CSV row {index} has an unrecognized OTPAuth value; retained as a concealed custom field.")
            items.append(BwItem(id=f"1pcsv-{index}", type=1, name=title, favorite=_csv_bool(value("favorite")), notes=value("notes") or None, fields=fields or None, login=login))
    warnings.append("1Password CSV is login-only; it cannot supply attachments, custom fields, cards, identities, or passkeys.")
    return VaultDocument("1password_csv", items, {"csv_columns": columns}, Path(path), warnings)
def _bw_custom_fields_to_sections(fields: list[Any] | None) -> list[dict[str, Any]]:
    if not fields:
        return []
    section_fields: list[dict[str, Any]] = []
    for index, field in enumerate(fields, 1):
        if not isinstance(field, dict):
            continue
        title = str(field.get("name") or f"Custom field {index}")
        value = field.get("value")
        if field.get("type") == 1:
            converted: Any = {"concealed": "" if value is None else str(value)}
        else:
            converted = "" if value is None else str(value)
        section_fields.append({"title": title, "id": str(uuid.uuid4()), "value": converted})
    return [{"title": "Additional Fields", "name": "Section_bitmerger", "fields": section_fields}] if section_fields else []


def _extract_onepassword_tags(fields: list[Any] | None) -> tuple[list[str], list[Any]]:
    """Recover adapter tag fields without polluting 1Password custom sections."""
    tags: list[str] = []
    remaining: list[Any] = []
    for field in fields or []:
        if isinstance(field, dict) and field.get("name") == "1Password tag":
            value = str(field.get("value") or "").strip()
            if value and value not in tags:
                tags.append(value)
        else:
            remaining.append(field)
    return tags, remaining


def _item_to_onepassword(item: BwItem) -> dict[str, Any]:
    """Create a valid 1PUX item with all portable fields represented."""
    category = _BW_CATEGORY_TO_ONEPASSWORD.get(item.type, "003")
    urls = []
    if item.login:
        urls = [{"label": "", "url": uri.uri} for uri in item.login.uris if uri.uri]
    tags, portable_fields = _extract_onepassword_tags(item.fields)
    details: dict[str, Any] = {"notesPlain": item.notes or "", "sections": _bw_custom_fields_to_sections(portable_fields)}
    if item.login:
        login_fields: list[dict[str, Any]] = []
        if item.login.username:
            login_fields.append({"value": item.login.username, "id": "username", "name": "username", "fieldType": "T", "designation": "username"})
        if item.login.password:
            login_fields.append({"value": item.login.password, "id": "password", "name": "password", "fieldType": "P", "designation": "password"})
        details["loginFields"] = login_fields
    if item.card:
        card_fields = [{"title": key, "id": str(uuid.uuid4()), "value": {"concealed": str(value)} if key in {"number", "code"} else str(value)} for key, value in item.card.items() if value not in (None, "")]
        if card_fields:
            details["sections"].append({"title": "Credit Card", "name": "Section_credit_card", "fields": card_fields})
    if item.identity:
        identity_fields = [{"title": key, "id": str(uuid.uuid4()), "value": str(value)} for key, value in item.identity.items() if value not in (None, "")]
        if identity_fields:
            details["sections"].append({"title": "Identity", "name": "Section_identity", "fields": identity_fields})
    if item.sshKey:
        key_fields = [{"title": label, "id": str(uuid.uuid4()), "value": {"concealed": value} if label == "privateKey" else value} for label, value in (("publicKey", item.sshKey.publicKey), ("privateKey", item.sshKey.privateKey), ("keyFingerprint", item.sshKey.keyFingerprint)) if value]
        if key_fields:
            details["sections"].append({"title": "SSH Key", "name": "Section_ssh", "fields": key_fields})
    return {
        "uuid": str(uuid.uuid4()),
        "favIndex": 1 if item.favorite else 0,
        "createdAt": int(time.time()),
        "updatedAt": int(time.time()),
        "state": "active",
        "categoryUuid": category,
        "overview": {"title": item.name, "url": urls[0]["url"] if urls else "", "urls": urls, "tags": tags},
        "details": details,
    }


def save_bitwarden(path: Path, items: Iterable[BwItem], source_data: dict[str, Any] | None = None) -> Path:
    """Write an atomic Bitwarden JSON export without Bitmerger-only metadata."""
    data = copy.deepcopy(source_data or {})
    # Never leak adapter provenance into an import file.
    clean_items: list[dict[str, Any]] = []
    for item in items:
        cloned = copy.deepcopy(item)
        cloned.extra = {key: value for key, value in cloned.extra.items() if not key.startswith("_bitmerger_")}
        clean_items.append(cloned.to_dict())
    data["encrypted"] = False
    data["items"] = clean_items
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    with temporary.open("r", encoding="utf-8") as handle:
        json.load(handle)
    temporary.replace(path)
    path.chmod(0o600)
    return path


def save_1password(path: Path, items: Iterable[BwItem], account_name: str = "Bitmerger Cleaned Vault") -> Path:
    """Write an unencrypted 1PUX archive with a single cleaned vault.

    The archive follows 1Password's documented export.data/export.attributes
    layout.  It intentionally contains no attachment payloads: Bitwarden JSON
    exports do not include them, and the merge report calls this out.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    account_uuid = str(uuid.uuid4())
    vault_uuid = str(uuid.uuid4())
    export_data = {
        "accounts": [{
            "attrs": {"accountName": account_name, "name": account_name, "uuid": account_uuid, "domain": ""},
            "vaults": [{
                "attrs": {"uuid": vault_uuid, "desc": "Generated locally by Bitmerger", "name": account_name, "type": "P"},
                "items": [_item_to_onepassword(item) for item in items],
            }],
        }]
    }
    attributes = {"version": 3, "description": "1Password Unencrypted Export", "createdAt": int(time.time())}
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file_handle:
        with zipfile.ZipFile(file_handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("export.attributes", json.dumps(attributes, indent=2, ensure_ascii=False))
            archive.writestr("export.data", json.dumps(export_data, indent=2, ensure_ascii=False))
    with zipfile.ZipFile(temporary) as archive:
        if set(("export.attributes", "export.data")) - set(archive.namelist()):
            raise VaultFormatError("Could not validate generated 1Password archive")
        json.loads(archive.read("export.data"))
    temporary.replace(path)
    path.chmod(0o600)
    return path


def _dedupe_strictly(items: list[BwItem], threshold: float) -> tuple[list[BwItem], int, int]:
    """Merge only clusters at or above threshold, preserving all conflicts."""
    clusters, _comparisons = find_duplicates_by_type(items, threshold=threshold, fast=False)
    approved = [cluster for cluster in clusters if cluster_confidence(cluster) >= threshold]
    merged_ids: set[str] = set()
    for cluster in approved:
        primary = cluster[pick_primary(cluster)]
        for candidate in cluster:
            if candidate is primary:
                continue
            primary, _ = merge_items(primary, candidate)
            merged_ids.add(candidate.id)
    return [item for item in items if item.id not in merged_ids], len(merged_ids), len(clusters)


def merge_vaults(
    bitwarden_path: Path,
    onepassword_path: Path,
    output_dir: Path,
    threshold: float = 0.95,
    onepassword_csv_path: Path | None = None,
    *,
    overwrite: bool = False,
) -> DualMergeResult:
    """Merge two source vaults and produce fresh Bitwarden JSON + 1Password 1PUX.

    A high default threshold is intentional: any non-exact or ambiguous cluster
    remains as separate records in both outputs rather than risking account loss.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")
    bitwarden = load_document(Path(bitwarden_path))
    onepassword = load_document(Path(onepassword_path))
    csv_document = load_document(Path(onepassword_csv_path)) if onepassword_csv_path else None
    if bitwarden.format != "bitwarden":
        raise VaultFormatError("The Bitwarden input must be a Bitwarden JSON export")
    if onepassword.format != "1password":
        raise VaultFormatError("The 1Password input must be a .1pux export")
    if csv_document and csv_document.format != "1password_csv":
        raise VaultFormatError("The optional 1Password CSV input must be a CSV export")
    csv_items = copy.deepcopy(csv_document.items) if csv_document else []
    combined = copy.deepcopy(bitwarden.items) + copy.deepcopy(onepassword.items) + csv_items
    warnings = bitwarden.warnings + onepassword.warnings + (csv_document.warnings if csv_document else [])
    final_items, merged_count, cluster_count = _dedupe_strictly(combined, threshold)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bw_output, onepassword_output, report_path = expected_merge_outputs(output_dir)
    source_paths = {bitwarden_path.resolve(), onepassword_path.resolve()}
    if onepassword_csv_path:
        source_paths.add(Path(onepassword_csv_path).resolve())
    collisions = [path for path in (bw_output, onepassword_output, report_path) if path.resolve() in source_paths]
    if collisions:
        names = ", ".join(path.name for path in collisions)
        raise VaultFormatError(f"Output path collides with selected source file(s): {names}")
    existing = [path for path in (bw_output, onepassword_output, report_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise VaultFormatError(f"Refusing to overwrite existing output(s): {names}")

    # Build and validate every plaintext artifact in a private staging directory
    # before exposing even one result in the requested output folder.
    with tempfile.TemporaryDirectory(prefix=".bitmerger-staging-", dir=output_dir) as stage_name:
        stage = Path(stage_name)
        staged_bw, staged_1p, staged_report = expected_merge_outputs(stage)
        save_bitwarden(staged_bw, final_items, bitwarden.raw_data)
        save_1password(staged_1p, final_items)
        report = {
            "input_count": len(combined), "output_count": len(final_items), "merged_count": merged_count,
            "candidate_clusters": cluster_count, "threshold": threshold, "warnings": warnings,
            "bitwarden_output": str(bw_output), "onepassword_output": str(onepassword_output),
            "safety": "Only clusters at or above the configured confidence threshold were merged. Conflicting field values are retained in notes.",
        }
        staged_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        json.loads(staged_report.read_text(encoding="utf-8"))
        staged_report.chmod(0o600)
        staged_bw.replace(bw_output)
        staged_1p.replace(onepassword_output)
        staged_report.replace(report_path)
    return DualMergeResult(bw_output, onepassword_output, report_path, len(combined), len(final_items), merged_count, cluster_count, warnings)
