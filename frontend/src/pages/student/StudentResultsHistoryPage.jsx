import SkeletonPage from "../../ui/SkeletonPage";

export default function StudentResultsHistoryPage() {
  return (
    <SkeletonPage
      title="Results History"
      subtitle="Previous assessments and recommendations."
      empty
      emptyTitle="No past results"
      emptyDescription="Your completed assessments will appear here."
    />
  );
}
