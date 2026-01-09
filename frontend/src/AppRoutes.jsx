// src/AppRoutes.jsx
import { Routes, Route, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";
import ProtectedRoute from "./components/ProtectedRoute";
import LoadingScreen from "./components/LoadingScreen";
import GuardianVerifyPage from "./pages/guardian/GuardianVerifyPage";

/* ======================
   Lazy-loaded Pages
   ====================== */

/** Public pages */
const HomePage = lazy(() => import("./pages/HomePage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const PricingPage = lazy(() => import("./pages/PricingPage"));
const SignupPage = lazy(() => import("./pages/SignupPage"));

/** Admin pages */
const AdminHomePage = lazy(() => import("./pages/AdminHomePage"));
const AdminCareerClustersPage = lazy(() =>
  import("./pages/admin/AdminCareerClustersPage")
);
const AdminCareersPage = lazy(() => import("./pages/admin/AdminCareersPage"));
const AdminKeySkillsPage = lazy(() =>
  import("./pages/admin/AdminKeySkillsPage")
);
const AdminMappingsPage = lazy(() => import("./pages/admin/AdminMappingsPage"));
const AdminBulkUploadPage = lazy(() =>
  import("./pages/admin/AdminBulkUploadPage")
);

/** Student pages */
const StudentDashboardPage = lazy(() => import("./pages/StudentDashboardPage"));
const StudentConsentPage = lazy(() => import("./pages/StudentConsentPage"));

const StudentOnboardingPage = lazy(() =>
  import("./pages/student/StudentOnboardingPage")
);
const StudentAssessmentIntroPage = lazy(() =>
  import("./pages/student/StudentAssessmentIntroPage")
);
const StudentAssessmentRunPage = lazy(() =>
  import("./pages/student/StudentAssessmentRunPage")
);
const StudentAssessmentSubmitPage = lazy(() =>
  import("./pages/student/StudentAssessmentSubmitPage")
);
const StudentResultsPage = lazy(() => import("./pages/student/StudentResultsPage"));
const StudentResultsHistoryPage = lazy(() =>
  import("./pages/student/StudentResultsHistoryPage")
);
const StudentCareerDetailPage = lazy(() =>
  import("./pages/student/StudentCareerDetailPage")
);
const StudentReportPage = lazy(() => import("./pages/student/StudentReportPage"));

/* ======================
   Fallback
   ====================== */
function NotFound() {
  return (
    <div style={{ padding: 24 }}>
      <h2>404</h2>
      <p>Page not found. (NOTFOUND_FROM_APPROUTES)</p>
    </div>
  );
}

/* ======================
   Routes
   ====================== */
export default function AppRoutes() {
  return (
    <Suspense fallback={<LoadingScreen label="Loading page…" />}>
      <Routes>
        <Route
          path="/__routes_probe"
          element={<div style={{ padding: 24 }}>ROUTES PROBE OK</div>}
        />

        {/* ======================
           Public Routes
           ====================== */}
        <Route path="/" element={<HomePage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/guardian/verify" element={<GuardianVerifyPage />} />
		<Route path="/signup" element={<SignupPage />} />

        {/* ======================
           Admin Routes
           ====================== */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminHomePage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/career-clusters"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminCareerClustersPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/careers"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminCareersPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/key-skills"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminKeySkillsPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/mappings"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminMappingsPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/bulk-upload"
          element={
            <ProtectedRoute allowRoles={["admin"]}>
              <AdminBulkUploadPage />
            </ProtectedRoute>
          }
        />

        {/* ======================
           Student Routes
           ====================== */}
        <Route
          path="/student/dashboard"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentDashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/__probe2"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <div style={{ padding: 24 }}>STUDENT PROBE2 OK</div>
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/consent"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentConsentPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/onboarding"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentOnboardingPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/assessment"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentAssessmentIntroPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/assessment/run/:attemptId"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentAssessmentRunPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/assessment/submit/:attemptId"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentAssessmentSubmitPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/results/latest"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentResultsPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/results/history"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentResultsHistoryPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/careers/:careerId"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentCareerDetailPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student/reports/:reportId"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <StudentReportPage />
            </ProtectedRoute>
          }
        />

        {/* ======================
           Friendly Aliases
           ====================== */}
        <Route path="/student" element={<Navigate to="/student/dashboard" replace />} />

        {/* ======================
           Catch-all
           ====================== */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
