import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

export default function StudentCareerDetailPage() {
  return (
    <SkeletonPage
      title="Career Details"
      subtitle="Why this career matches your profile."
      actions={
        <>
          <Button variant="secondary">Back</Button>
          <Button>Shortlist</Button>
        </>
      }
    >
      <p>Career explanation, pathway, feasibility, CPS fit.</p>
    </SkeletonPage>
  );
}
