import { RoutePage } from "@/components/RoutePage";

export default async function Page({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = await params;
  return <RoutePage routeKey="opponents" recordId={teamId} />;
}
