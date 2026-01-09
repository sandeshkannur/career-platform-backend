// src/pages/AdminHomePage.jsx
import { Link } from "react-router-dom";
import SkeletonPage from "../ui/SkeletonPage";
import Button from "../ui/Button";
import { useSession } from "../hooks/useSession";

export default function AdminHomePage() {
  const { logout, sessionUser } = useSession();

  return (
    <SkeletonPage
      title="Admin Console"
      subtitle={
        sessionUser?.full_name
          ? `Welcome, ${sessionUser.full_name}. Manage master data and mappings.`
          : "Manage master data and mappings."
      }
      actions={<Button onClick={logout}>Logout</Button>}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Link to="/admin/career-clusters">
          <Button style={{ width: "100%" }}>Career Clusters</Button>
        </Link>

        <Link to="/admin/careers">
          <Button style={{ width: "100%" }}>Careers</Button>
        </Link>

        <Link to="/admin/key-skills">
          <Button style={{ width: "100%" }}>Key Skills</Button>
        </Link>

        <Link to="/admin/mappings">
          <Button style={{ width: "100%" }}>Mappings</Button>
        </Link>

        <Link to="/admin/bulk-upload">
          <Button style={{ width: "100%" }}>Bulk Upload</Button>
        </Link>

        <div style={{ marginTop: 10 }}>
          <Link to="/">← Home</Link>
        </div>
      </div>
    </SkeletonPage>
  );
}
