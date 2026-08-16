import time

import streamlit as st

from nexus.operator.queries import (
    get_attempts,
    get_dead_letter_items,
    get_recent_events,
    get_recent_failures,
    get_system_summary,
    get_work_item,
    get_work_timeline,
    get_retrying_items,
    get_queued_items,
    get_running_items,
    get_succeeded_items,
)

from nexus.storage.database import (
    initialize,
    connect,
)

from nexus.core.cache_manager import (
    CacheManager,
    CacheExpiredError,
)

from nexus.core.degradation import (
    DegradationManager,
)

from nexus.core.order import (
    classify_sequence,
)


# =========================================================
# INITIALIZATION
# =========================================================

initialize()

st.set_page_config(
    page_title="NEXUS Operator",
    page_icon="N",
    layout="wide",
)


# =========================================================
# LIGHT THEME
# =========================================================

st.markdown(
    """
<style>

.stApp {
    background-color: #f6f8fb;
    color: #172033;
}

[data-testid="stHeader"] {
    background-color: #f6f8fb;
}

[data-testid="stToolbar"] {
    visibility: visible;
}


/* =====================================================
   HEADER
   ===================================================== */

.nexus-header {
    padding: 8px 0 28px 0;
}

.nexus-title {
    font-size: 44px;
    font-weight: 850;
    letter-spacing: -1.8px;
    color: #172033;
    line-height: 1;
}

.nexus-subtitle {
    margin-top: 9px;
    font-size: 15px;
    color: #6b7280;
}


/* =====================================================
   SECTION LABEL
   ===================================================== */

.section-label {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 1.2px;
    color: #64748b;
    text-transform: uppercase;
    margin-bottom: 6px;
}


/* =====================================================
   METRIC CARDS
   ===================================================== */

.status-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px 20px;
    min-height: 112px;
    box-shadow: 0 2px 7px rgba(15, 23, 42, 0.04);
    border-top: 4px solid #2563eb;
}

.status-title {
    font-size: 11px;
    font-weight: 800;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.status-value {
    font-size: 34px;
    font-weight: 850;
    margin-top: 8px;
    color: #172033;
}


/* =====================================================
   SIGNAL CARDS
   ===================================================== */

.signal-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 19px 21px;
    margin-bottom: 18px;
    box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
    border-left: 4px solid #2563eb;
}

.signal-title {
    font-size: 18px;
    font-weight: 800;
    color: #172033;
}

.signal-description {
    color: #64748b;
    font-size: 13px;
    margin-top: 5px;
}


/* =====================================================
   BUTTON
   ===================================================== */

.stButton > button {
    border-radius: 9px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
    color: #1e293b;
    font-weight: 650;
    padding: 7px 16px;
}

.stButton > button:hover {
    border-color: #2563eb;
    color: #2563eb;
    background: #eff6ff;
}


/* =====================================================
   TABS
   ===================================================== */

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #e2e8f0;
}

.stTabs [data-baseweb="tab"] {
    color: #64748b;
    font-weight: 650;
    padding: 10px 16px;
}

.stTabs [aria-selected="true"] {
    color: #2563eb;
}


/* =====================================================
   DATAFRAMES
   ===================================================== */

[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
}


/* =====================================================
   ALERTS
   ===================================================== */

[data-testid="stAlert"] {
    border-radius: 10px;
}


/* =====================================================
   DIVIDERS
   ===================================================== */

hr {
    border-color: #e2e8f0;
}

</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
<div class="nexus-header">
    <div class="nexus-title">NEXUS</div>
    <div class="nexus-subtitle">
        Reliable Work Orchestration &amp; Operator Control Plane
    </div>
</div>
""",
    unsafe_allow_html=True,
)


if st.button("↻ Refresh"):
    st.rerun()


# =========================================================
# SYSTEM OVERVIEW
# =========================================================

summary = get_system_summary()

st.markdown(
    '<div class="section-label">System Health</div>',
    unsafe_allow_html=True,
)

st.caption(
    "Current durable work state across the NEXUS system."
)


c1, c2, c3, c4, c5 = st.columns(5)

metrics = [
    ("TOTAL WORK", summary["work"]["total"]),
    ("QUEUED", summary["work"]["queued"]),
    ("RUNNING", summary["work"]["running"]),
    ("SUCCEEDED", summary["work"]["succeeded"]),
    ("DEAD LETTERED", summary["work"]["dead_lettered"]),
]


# =========================================================
# COLORED METRIC CARDS
# =========================================================

metric_colors = {
    "TOTAL WORK": "#2563eb",
    "QUEUED": "#f59e0b",
    "RUNNING": "#7c3aed",
    "SUCCEEDED": "#16a34a",
    "DEAD LETTERED": "#dc2626",
}


for column, (title, value) in zip(
    [c1, c2, c3, c4, c5],
    metrics,
):

    with column:

        accent = metric_colors.get(
            title,
            "#2563eb",
        )

        card_html = (
            f'<div class="status-card" '
            f'style="border-top-color:{accent};">'
            f'<div class="status-title">{title}</div>'
            f'<div class="status-value">{value}</div>'
            f'</div>'
        )

        st.markdown(
            card_html,
            unsafe_allow_html=True,
        )


st.divider()


# =========================================================
# WORK QUEUE
# =========================================================

st.subheader("Work Queue")

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Queued",
        "Running",
        "Succeeded",
        "Dead Lettered",
    ]
)


with tab1:

    queued = get_queued_items(
        limit=100
    )

    if queued:

        st.dataframe(
            queued,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No queued work."
        )


with tab2:

    running = get_running_items(
        limit=100
    )

    if running:

        st.dataframe(
            running,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No running work."
        )


with tab3:

    succeeded = get_succeeded_items(
        limit=100
    )

    if succeeded:

        st.dataframe(
            succeeded,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No succeeded work."
        )


with tab4:

    dead_lettered = get_dead_letter_items(
        limit=100
    )

    if dead_lettered:

        st.dataframe(
            dead_lettered,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No dead-lettered work."
        )


# =========================================================
# RETRYING WORK
# =========================================================

st.divider()

st.subheader("Retrying Work")

retrying = get_retrying_items(
    limit=100
)

if retrying:

    st.dataframe(
        retrying,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "No work is currently waiting for retry."
    )


# =========================================================
# RELIABILITY SIGNALS
# =========================================================

st.divider()

st.subheader("Reliability Signals")

st.caption(
    "Operator-visible evidence for consistency, freshness, "
    "degradation and ordering certainty."
)


r8, r9, r10, r13 = st.tabs(
    [
        "Consistency",
        "Cache Freshness",
        "Degradation",
        "Order Certainty",
    ]
)


# =========================================================
# R8 — CONSISTENCY
# =========================================================

with r8:

    st.markdown(
        """
<div class="signal-card">
    <div class="signal-title">
        Consistency Disagreements
    </div>
    <div class="signal-description">
        Conflicting values are reported instead of
        being silently corrected.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    connection = connect()

    try:

        rows = connection.execute(
            """
            SELECT
                event_type,
                subject_type,
                subject_id,
                severity,
                decision,
                reason,
                before_json,
                after_json,
                message,
                occurred_at
            FROM events
            WHERE event_type =
                'CONSISTENCY_DISAGREEMENT'
            ORDER BY occurred_at DESC
            LIMIT 50
            """
        ).fetchall()

        disagreements = [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


    if disagreements:

        st.dataframe(
            disagreements,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.success(
            "No consistency disagreements detected."
        )


# =========================================================
# R9 — CACHE FRESHNESS
# =========================================================

with r9:

    st.markdown(
        """
<div class="signal-card">
    <div class="signal-title">
        Cache Freshness
    </div>
    <div class="signal-description">
        Cached values carry their age and expired
        values are refused.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


    if "dashboard_cache" not in st.session_state:

        st.session_state.dashboard_cache = (
            CacheManager()
        )

        st.session_state.dashboard_cache.set(
            "service-status",
            "HEALTHY",
        )

        st.session_state.dashboard_cache.set(
            "inventory",
            42,
        )


    cache = (
        st.session_state.dashboard_cache
    )


    max_age = st.number_input(
        "Maximum allowed cache age (seconds)",
        min_value=0.01,
        value=5.0,
        step=1.0,
        key="cache_max_age",
    )


    cache_rows = []


    for key in [
        "service-status",
        "inventory",
    ]:

        inspection = cache.inspect(
            key
        )

        if inspection is None:
            continue


        try:

            result = cache.get(
                key,
                max_age_seconds=max_age,
            )

            status = "FRESH"
            served = "YES"


        except CacheExpiredError:

            result = inspection

            status = "EXPIRED"
            served = "NO"


        cache_rows.append(
            {
                "key": key,
                "value": result["value"],
                "age_seconds": round(
                    result["age_seconds"],
                    3,
                ),
                "max_age_seconds": max_age,
                "status": status,
                "served": served,
            }
        )


    if cache_rows:

        st.dataframe(
            cache_rows,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No cached values are currently available."
        )


# =========================================================
# R10 — HONEST DEGRADATION
# =========================================================

with r10:

    st.markdown(
        """
<div class="signal-card">
    <div class="signal-title">
        Honest Degradation
    </div>
    <div class="signal-description">
        When a dependency is unavailable, NEXUS
        exposes the fallback and explicitly marks
        the result as degraded.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


    degradation = (
        DegradationManager()
    )


    # -----------------------------------------------------
    # Healthy dependency
    # -----------------------------------------------------

    def available_dependency():

        return {
            "inventory": 42,
            "source": "live",
        }


    # -----------------------------------------------------
    # Failed dependency
    # -----------------------------------------------------

    def unavailable_dependency():

        raise ConnectionError(
            "inventory service unavailable"
        )


    healthy = degradation.resolve(
        available_dependency,
        fallback={
            "inventory": 40,
            "source": "last-known-value",
        },
    )


    degraded = degradation.resolve(
        unavailable_dependency,
        fallback={
            "inventory": 40,
            "source": "last-known-value",
        },
    )


    d1, d2 = st.columns(2)


    # =====================================================
    # HEALTHY SCENARIO
    # =====================================================

    with d1:

        st.markdown(
            "### Healthy Scenario"
        )

        st.success(
            "DEPENDENCY AVAILABLE"
        )

        st.json(
            {
                "status": healthy.status,
                "inventory": healthy.value[
                    "inventory"
                ],
                "source": healthy.value[
                    "source"
                ],
            }
        )


    # =====================================================
    # FAILURE SCENARIO
    # =====================================================

    with d2:

        st.markdown(
            "### Dependency Failure Scenario"
        )

        st.warning(
            "DEGRADED"
        )

        st.json(
            {
                "status": degraded.status,
                "fallback": degraded.value,
                "reason": degraded.reason,
                "dependency_available":
                    degraded.dependency_available,
            }
        )


    st.info(
        "R10 demonstration: when the dependency becomes "
        "unavailable, NEXUS serves an explicitly marked "
        "last-known fallback instead of presenting it "
        "as live data."
    )


# =========================================================
# R13 — ORDER CERTAINTY
# =========================================================

with r13:

    st.markdown(
        """
<div class="signal-card">
    <div class="signal-title">
        Order Certainty
    </div>
    <div class="signal-description">
        NEXUS distinguishes proven sequence from
        records that are merely adjacent on screen.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


    demo_records = [
        {
            "id": "record-A",
            "sequence": 1,
        },
        {
            "id": "record-B",
        },
        {
            "id": "record-C",
            "sequence": 3,
        },
    ]


    order_result = classify_sequence(
        demo_records
    )


    known_rows = []

    for item in order_result[
        "known_order"
    ]:

        known_rows.append(
            {
                "relationship":
                    f"{item['before']} → "
                    f"{item['after']}",
                "order": "KNOWN",
                "basis": item["basis"],
            }
        )


    unknown_rows = []

    for item in order_result[
        "unknown_order"
    ]:

        unknown_rows.append(
            {
                "relationship":
                    f"{item['left']} ↔ "
                    f"{item['right']}",
                "order": "UNKNOWN",
                "basis": item["basis"],
            }
        )


    st.write(
        "Known ordering"
    )


    if known_rows:

        st.dataframe(
            known_rows,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No ordering relationships are currently known."
        )


    st.write(
        "Uncertain ordering"
    )


    if unknown_rows:

        st.dataframe(
            unknown_rows,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No uncertain ordering relationships."
        )


    st.info(
        "Display adjacency alone is never treated as "
        "proof of ordering."
    )


# =========================================================
# WORK INSPECTION
# =========================================================

st.divider()

st.subheader(
    "Inspect Work"
)


work_id = st.text_input(
    "Enter Work ID",
    placeholder="e.g. retry-success-...",
)


if work_id:

    work = get_work_item(
        work_id
    )


    if work is None:

        st.error(
            "Work item not found."
        )


    else:

        st.json(
            work
        )


        st.subheader(
            "Attempts"
        )


        attempts = get_attempts(
            work_id
        )


        if attempts:

            st.dataframe(
                attempts,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "No attempts recorded."
            )


        st.subheader(
            "Event Timeline"
        )


        timeline = get_work_timeline(
            work_id
        )


        if timeline:

            for event in timeline:

                timestamp = time.strftime(
                    "%H:%M:%S",
                    time.localtime(
                        event["occurred_at"]
                    ),
                )


                st.write(
                    f"**{timestamp} — "
                    f"{event['event_type']}**"
                )


                st.caption(
                    f"{event.get('decision')} | "
                    f"{event.get('reason')}"
                )


                if event.get("message"):

                    st.write(
                        event["message"]
                    )


        else:

            st.info(
                "No events recorded for this work item."
            )


# =========================================================
# RECENT FAILURES
# =========================================================

st.divider()

st.subheader(
    "Recent Failures"
)


failures = get_recent_failures(
    limit=30
)


if failures:

    st.dataframe(
        failures,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.success(
        "No recent failures."
    )


# =========================================================
# RECENT EVENTS
# =========================================================

st.divider()

st.subheader(
    "Recent Events"
)


events = get_recent_events(
    limit=50
)


if events:

    st.dataframe(
        events,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "No recent events."
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "NEXUS records durable work state, attempt history, "
    "structured events, consistency disagreements, "
    "cache freshness and operator-visible reliability signals."
)