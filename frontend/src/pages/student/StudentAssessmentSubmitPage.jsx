import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function StudentAssessmentSubmitPage() {
  return (
    <SkeletonPage
      title="Submit Assessment"
      subtitle="Once submitted, results will be generated."
      actions={<Button>Confirm & Submit</Button>}
    >
      <p>Summary of attempted questions.</p>
    </SkeletonPage>
  );
}
