import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function AdminBulkUploadPage() {
  return (
    <SkeletonPage
      title="Bulk Upload"
      subtitle="Upload CSVs for master data."
      actions={<Button>Upload CSV</Button>}
      empty
      emptyTitle="No uploads yet"
      emptyDescription="Upload files to populate the system."
    />
  );
}
