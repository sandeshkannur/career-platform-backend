// src/pages/student/StudentReportPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";
import { getStudentReport } from "../../api/reports";

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();

  URL.revokeObjectURL(url);
}

export default function StudentReportPage() {
  const params = useParams();
  const studentId = useMemo(() => {
  // Route is /student/reports/:reportId (which is actually student_id)
  const raw = params.reportId;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
	}, [params.reportId]);

  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);

  // Special states
  const [notReady, setNotReady] = useState(false); // 404
  const [unsupported, setUnsupported] = useState(false); // 400

  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!studentId) return;

      setLoading(true);
      setReport(null);
      setNotReady(false);
      setUnsupported(false);
      setError(null);

      try {
        const data = await getStudentReport(studentId);
        if (cancelled) return;
        setReport(data);
      } catch (e) {
        if (cancelled) return;

        const status = e?.status || e?.response?.status;

        if (status === 404) {
          setNotReady(true);
          return;
        }

        if (status === 400) {
          setUnsupported(true);
          return;
        }

        const message =
          e?.message ||
          e?.detail ||
          e?.response?.data?.detail ||
          "Failed to load report.";

        setError({ status, message, raw: e });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  const canDownloadJson = !!report && !loading;

  return (
    <SkeletonPage
      title="Assessment Report"
      subtitle="Report derived from your latest analytics snapshot."
      actions={
        <>
          <Button
            variant="secondary"
            disabled={!canDownloadJson}
            onClick={() => {
              if (!report) return;
              downloadJson(`student-report-${studentId}.json`, report);
            }}
          >
            Download JSON
          </Button>

          {/* PDF is explicitly out-of-scope now */}
          <Button disabled title="PDF generation is planned later">
            Download PDF
          </Button>
        </>
      }
    >
      {!studentId && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          Invalid student id in route.
        </div>
      )}

      {studentId && loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          Loading report…
        </div>
      )}

      {studentId && notReady && !loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            Report not ready yet
          </div>
          <div style={{ fontSize: 14 }}>
            Complete an assessment (or refresh after analytics are generated),
            then come back here.
          </div>
        </div>
      )}

      {studentId && unsupported && !loading && (
        <div
          style={{
            padding: 12,
            border: "1px solid #f3c27b",
            background: "#fff9ef",
            borderRadius: 8,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            Unsupported report version
          </div>
          <div style={{ fontSize: 14 }}>
            Your backend report/scoring version is not supported by this UI.
          </div>
        </div>
      )}

      {studentId && error && !loading && (
        <div
          style={{
            padding: 12,
            border: "1px solid #f3b4b4",
            background: "#fff6f6",
            borderRadius: 8,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            Failed to load report{error.status ? ` (HTTP ${error.status})` : ""}
          </div>
          <div style={{ fontSize: 14 }}>{error.message}</div>
          <div style={{ marginTop: 10 }}>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </div>
      )}

      {studentId && report && !loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>
            Report JSON (temporary preview)
          </div>
          <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
            {JSON.stringify(report, null, 2)}
          </pre>
        </div>
      )}
    </SkeletonPage>
  );
}
