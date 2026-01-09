import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function StudentResultsPage() {
  return (
    <SkeletonPage
      title="Your Career Results"
      subtitle="Top recommendations based on your assessment."
      actions={
        <>
          <Button variant="secondary">View History</Button>
          <Button>Download Report</Button>
        </>
      }
      empty
      emptyTitle="Results not ready"
      emptyDescription="Complete the assessment to view results."
    >
      {/* Career cards */}
    </SkeletonPage>
  );
}
