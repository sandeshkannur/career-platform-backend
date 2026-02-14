// src/AppRoutes.jsx
import { Routes, Route, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";
import ProtectedRoute from "./components/ProtectedRoute";
import LoadingScreen from "./components/LoadingScreen";
import GuardianVerifyPage from "./pages/guardian/GuardianVerifyPage";
import StudentContextPage from "./pages/student/StudentContextPage";
import DashboardLayout from "./layouts/DashboardLayout";

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
const StudentProfilePage = lazy(() => import("./pages/student/StudentProfilePage"));

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
          path="/student"
          element={
            <ProtectedRoute allowRoles={["student"]}>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/student/dashboard" replace />} />

          <Route path="dashboard" element={<StudentDashboardPage />} />

          <Route path="__probe2" element={<div style={{ padding: 24 }}>STUDENT PROBE2 OK</div>} />

          <Route path="consent" element={<StudentConsentPage />} />
          <Route path="onboarding" element={<StudentOnboardingPage />} />
          <Route path="context" element={<StudentContextPage />} />

          <Route path="assessment" element={<StudentAssessmentIntroPage />} />

          <Route path="assessment/run/:attemptId" element={<StudentAssessmentRunPage />} />
          <Route path="assessment/submit/:attemptId" element={<StudentAssessmentSubmitPage />} />

          <Route path="results" element={<Navigate to="/student/results/latest" replace />} />
          <Route path="results/latest" element={<StudentResultsPage />} />
          <Route path="results/history" element={<StudentResultsHistoryPage />} />

          <Route path="careers/:careerId" element={<StudentCareerDetailPage />} />
          <Route path="profile" element={<StudentProfilePage />} />
          <Route path="reports/:reportId" element={<StudentReportPage />} />
        </Route>


        {/* ======================
           Catch-all
           ====================== */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
