"""Database-level immutability guards for audit logs and memory versions."""

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from ..models.db_models import MemoryVersion


class AuditLogTamperError(Exception):
    """Raised when an attempt is made to modify or delete immutable audit ledger entries."""
    pass


def attach_immutability_guards(target_session_or_factory):
    """
    Registers SQLAlchemy event listeners to guarantee that records in the
    'memory_versions' table can NEVER be updated or deleted by application or admin tooling.
    """
    @event.listens_for(target_session_or_factory, "before_flush")
    def receive_before_flush(session, flush_context, instances):
        # Inspect dirty (modified) objects
        for obj in session.dirty:
            if isinstance(obj, MemoryVersion):
                state = inspect(obj)
                history_attrs = [attr.key for attr in state.attrs if attr.history.has_changes()]
                if history_attrs:
                    raise AuditLogTamperError(
                        f"Compliance Violation: MemoryVersion records are strictly immutable. "
                        f"Attempted mutation of version {obj.id} on attributes {history_attrs}."
                    )

        # Inspect deleted objects
        # Note: GDPR Right to be Forgotten mandates permanent erasure of all user personal data when explicitly invoked by data subject.
        # Unauthorized deletion of audit ledgers without explicit GDPR context is rejected.
        is_gdpr_purge = bool(session.info.get("gdpr_purge_authorized"))
        for obj in session.deleted:
            if isinstance(obj, MemoryVersion) and not is_gdpr_purge:
                raise AuditLogTamperError(
                    f"Compliance Violation: MemoryVersion records cannot be deleted. "
                    f"Attempted deletion of version record {obj.id}."
                )
