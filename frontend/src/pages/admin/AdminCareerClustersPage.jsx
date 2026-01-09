import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function AdminCareerClustersPage() {
  return (
    <SkeletonPage
      title="Career Clusters"
      subtitle="Manage career clusters."
      actions={<Button>Create Cluster</Button>}
      empty
      emptyTitle="No clusters found"
      emptyDescription="Create or upload career clusters."
    />
  );
}
