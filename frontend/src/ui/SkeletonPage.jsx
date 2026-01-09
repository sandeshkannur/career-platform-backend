// src/ui/SkeletonPage.jsx
import Page from "./Page";
import Card from "./Card";
import Button from "./Button";

export default function SkeletonPage({
  title,
  subtitle,
  actions = null,
  children,
  loading = false,
  error = "",
  onRetry = null,
  empty = false,
  emptyTitle = "Nothing here yet",
  emptyDescription = "No data available.",
  emptyActions = null,
  footer = null,
  maxWidth = "900px",
}) {
  return (
    <Page maxWidth={maxWidth}>
      <Card>
        <div style={styles.headerRow}>
          <div style={{ minWidth: 0 }}>
            <h1 style={styles.title}>{title}</h1>
            {subtitle ? <p style={styles.subtitle}>{subtitle}</p> : null}
          </div>

          <div style={styles.actions}>{actions}</div>
        </div>

        <div style={styles.divider} />

        {loading ? (
          <div style={styles.stateWrap}>
            <p style={styles.stateTitle}>Loading…</p>
            <p style={styles.stateText}>Please wait.</p>
          </div>
        ) : error ? (
          <div style={styles.stateWrap}>
            <p style={styles.stateTitle}>Something went wrong</p>
            <p style={styles.stateText}>{error}</p>
            {onRetry ? (
              <div style={{ marginTop: 12 }}>
                <Button onClick={onRetry}>Retry</Button>
              </div>
            ) : null}
          </div>
        ) : empty ? (
          <div style={styles.stateWrap}>
            <p style={styles.stateTitle}>{emptyTitle}</p>
            <p style={styles.stateText}>{emptyDescription}</p>
            {emptyActions ? <div style={{ marginTop: 12 }}>{emptyActions}</div> : null}
          </div>
        ) : (
          <div style={styles.body}>{children}</div>
        )}

        {footer ? (
          <>
            <div style={styles.divider} />
            <div style={styles.footer}>{footer}</div>
          </>
        ) : null}
      </Card>
    </Page>
  );
}

const styles = {
  headerRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  title: {
    margin: 0,
    fontSize: 22,
    lineHeight: "28px",
  },
  subtitle: {
    margin: "6px 0 0",
    color: "#666",
    fontSize: 14,
    lineHeight: "20px",
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "flex-end",
  },
  divider: {
    height: 1,
    background: "#eee",
    margin: "14px 0",
  },
  body: {
    display: "block",
  },
  stateWrap: {
    padding: "18px 0",
    textAlign: "center",
  },
  stateTitle: {
    margin: 0,
    fontSize: 16,
    fontWeight: 600,
  },
  stateText: {
    margin: "6px 0 0",
    color: "#666",
    fontSize: 14,
  },
  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
};
