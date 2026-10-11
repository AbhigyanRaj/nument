// A developer-only page showing every UI component, used to check the design.

import { Badge, Eyebrow, SectionHeading, StatRow } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";

/** Dev-only gallery for checking primitives against design-kit/components/gallery.html. */
export default function KitGallery() {
  return (
    <div className="container-kit flex flex-col gap-12 py-16">
      <SectionHeading title={"Component gallery"} intro="Primitives rendered with kit tokens." />
      <div className="flex flex-wrap gap-3">
        <Button variant="ink">Ink</Button>
        <Button variant="soft">Soft</Button>
        <Button variant="hero-primary">Hero primary</Button>
        <Button variant="hero-outline">Hero outline</Button>
        <Button variant="outline" arrow>
          Outline
        </Button>
        <Button variant="app">App</Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {(["indigo", "green", "orange", "pink", "yellow", "red", "grey"] as const).map((t) => (
          <Badge key={t} tone={t}>
            {t}
          </Badge>
        ))}
      </div>
      <Eyebrow>Eyebrow label</Eyebrow>
      <div className="max-w-md">
        <StatRow label="orders planned" value="150" />
        <StatRow label="checks per plan" value="5" />
      </div>
    </div>
  );
}
