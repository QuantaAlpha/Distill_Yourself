#!/usr/bin/env python3
"""Thin wrapper — delegates to chatview.cli for backward compatibility.

Re-exports internal functions used by tests and external callers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chatview.cli import main

# Re-export functions used by tests
from chatview.commands.evolve import (  # noqa: F401
    _validate_evolve_data,
    _check_item,
    _read_evolve_cache,
    _write_evolve_cache,
    _merge_evolve_data,
    _delete_evolve_data,
    cmd_evolve_rules,
    cmd_evolve_signals,
    cmd_evolve_patterns,
    cmd_profile_digest,
    cmd_aggregates,
    cmd_evolve_write,
    cmd_evolve_sync,
)
from chatview.commands.corrections import (  # noqa: F401
    _data_corrections,
    cmd_corrections,
    _data_decisions,
    cmd_decisions,
    _data_errors,
    cmd_errors,
    _data_highlights,
    cmd_highlights,
)
from chatview.commands.analysis import (  # noqa: F401
    _init_index,
    _apply_filters,
    _get_filtered,
    _get_filtered_db,
    _get_messages_db,
    cmd_sessions,
    cmd_read,
    cmd_search,
    cmd_queries,
    cmd_stats,
    _data_files,
    cmd_files,
    cmd_refresh,
    cmd_install_skill,
)
from chatview.commands.twin import (  # noqa: F401
    cmd_twin_stats,
    cmd_twin_events,
    cmd_twin_cards,
    cmd_twin_traits,
    cmd_twin_write,
    cmd_twin_compile,
    cmd_twin_get,
    cmd_twin_search,
    cmd_twin_add,
    cmd_twin_edit,
    cmd_twin_link,
    cmd_twin_batch,
    cmd_twin_candidates,
)

if __name__ == "__main__":
    main()
