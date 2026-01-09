import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function AdminMappingsPage() {
  return (
    <SkeletonPage
      title="Skill Mappings"
      subtitle="Manage AQ → Skill → Key Skill mappings."
      actions={
        <>
          <Button variant="secondary">Validate</Button>
          <Button>Upload Mapping</Button>
        </>
      }
      empty
    />
  );
}
