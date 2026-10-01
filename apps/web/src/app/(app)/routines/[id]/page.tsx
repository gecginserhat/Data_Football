import { RoutePage } from "@/components/RoutePage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RoutePage routeKey="routines" recordId={id} />;
}
