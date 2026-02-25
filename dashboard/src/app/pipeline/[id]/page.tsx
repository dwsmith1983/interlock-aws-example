import { PipelineDetail } from "@/components/PipelineDetail";

export function generateStaticParams() {
  return [
    { id: "earthquake-silver" },
    { id: "earthquake-gold" },
    { id: "crypto-silver" },
    { id: "crypto-gold" },
  ];
}

export default async function PipelineDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PipelineDetail id={id} />;
}
