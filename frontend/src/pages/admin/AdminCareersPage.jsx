import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function AdminCareersPage() {
  return (
    <SkeletonPage
      title="Careers"
      subtitle="Manage careers and mappings."
      actions={
        <>
          <Button variant="secondary">Bulk Upload</Button>
          <Button>Create Career</Button>
        </>
      }
      empty
    />
  );
}
