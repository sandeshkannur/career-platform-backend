import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function AdminKeySkillsPage() {
  return (
    <SkeletonPage
      title="Key Skills"
      subtitle="Manage core and derived skills."
      actions={<Button>Create Key Skill</Button>}
      empty
    />
  );
}
