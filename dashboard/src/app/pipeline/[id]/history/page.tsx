import { HistoryPageContent } from "@/components/HistoryPageContent";

export function generateStaticParams() {
  return [
    { id: "earthquake-silver" },
    { id: "earthquake-gold" },
    { id: "crypto-silver" },
    { id: "crypto-gold" },
  ];
}

export default async function PipelineHistoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <HistoryPageContent id={id} />;
}
