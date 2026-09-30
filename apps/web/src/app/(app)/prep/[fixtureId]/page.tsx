import { RoutePage } from "@/components/RoutePage";

export default async function Page({ params }: { params: Promise<{ fixtureId: string }> }) {
  const { fixtureId } = await params;
  return <RoutePage routeKey="prep" recordId={fixtureId} />;
}
