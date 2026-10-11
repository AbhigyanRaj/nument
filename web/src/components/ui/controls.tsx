// Form controls and small UI pieces: inputs, selects, toggles, badges and more.

import * as AccordionPrimitive from "@radix-ui/react-accordion";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as SelectPrimitive from "@radix-ui/react-select";
import * as SliderPrimitive from "@radix-ui/react-slider";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Check, ChevronDown } from "lucide-react";
import {
  forwardRef,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";

import { cn } from "@/lib/utils";

/* ---------- Inputs ---------- */

// "pill" is the 44px auth/app input; "soft" is the 48px, 16px-radius form field (contact.md).
export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { shape?: "pill" | "soft"; invalid?: boolean }
>(function Input({ shape = "pill", invalid, className, ...props }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full border border-st bg-white text-base text-tx transition-[border-color,box-shadow] duration-150 outline-none placeholder:text-tx-muted sm:text-[15px]",
        "focus:border-indigo-300 focus:shadow-focus aria-invalid:border-red-300",
        shape === "pill" ? "h-11 rounded-full px-4" : "h-12 rounded-2xl border-st-secondary px-4",
        className,
      )}
      {...props}
    />
  );
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "w-full resize-none bg-transparent text-tx outline-none placeholder:text-tx-muted",
        className,
      )}
      {...props}
    />
  );
});

export function Field({
  label,
  children,
  hint,
  srOnly,
}: {
  label: string;
  children: (id: string) => ReactNode;
  hint?: string;
  srOnly?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={id}
        className={cn("text-caption font-medium text-tx-secondary", srOnly && "sr-only")}
      >
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-[13px] text-tx-tertiary">{hint}</p>}
    </div>
  );
}

/* ---------- Segmented control with a sliding pill (models.md §3.3) ---------- */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  tone = "dark",
  size = "md",
  label,
}: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  tone?: "dark" | "light";
  size?: "sm" | "md";
  label: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [box, setBox] = useState({ left: 0, width: 0 });
  useLayoutEffect(() => {
    const el = refs.current[value];
    if (el) setBox({ left: el.offsetLeft, width: el.offsetWidth });
  }, [value, options.length]);
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        "relative inline-flex items-center rounded-full border border-st-secondary bg-white p-1",
        tone === "light" && "border-0 bg-sf-secondary",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute top-1 bottom-1 rounded-full transition-all duration-[450ms] ease-pill",
          tone === "dark"
            ? "bg-tx shadow-[inset_0_0_12px_rgba(255,255,255,.3)]"
            : "bg-white shadow-[0_1px_3px_#00000014]",
        )}
        style={{ left: box.left, width: box.width }}
      />
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[option.value] = el;
            }}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "relative z-10 rounded-full whitespace-nowrap transition-colors duration-150",
              size === "sm" ? "min-h-8 px-3 py-1 text-[13px]" : "min-h-9 px-4 py-1.5 text-caption",
              active
                ? tone === "dark"
                  ? "font-medium text-sf"
                  : "font-medium text-tx"
                : "text-tx-tertiary hover:text-tx",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* ---------- Soft accordion (pricing.md §2.5, FAQ rows) ---------- */

export function SoftAccordion({
  items,
  defaultOpen,
}: {
  items: { id: string; title: ReactNode; body: ReactNode }[];
  defaultOpen?: string;
}) {
  return (
    <AccordionPrimitive.Root
      type="single"
      collapsible
      defaultValue={defaultOpen}
      className="flex w-full flex-col gap-2"
    >
      {items.map((item) => (
        <AccordionPrimitive.Item
          key={item.id}
          value={item.id}
          className="overflow-hidden border-b border-st-secondary md:rounded-2xl md:border-0 md:bg-sf/50"
        >
          <AccordionPrimitive.Header>
            <AccordionPrimitive.Trigger className="group flex min-h-11 w-full items-center justify-between gap-4 px-2 py-3 text-left text-[15px] leading-relaxed text-tx transition-colors duration-300 hover:text-tx-brand md:px-6 md:py-5 md:text-lg md:hover:bg-black/5">
              {item.title}
              <ChevronDown
                aria-hidden
                strokeWidth={1.5}
                className="size-5 shrink-0 text-tx-secondary transition-[transform,color] duration-300 group-hover:text-tx-accent group-data-[state=open]:rotate-180"
              />
            </AccordionPrimitive.Trigger>
          </AccordionPrimitive.Header>
          <AccordionPrimitive.Content className="accordion-content overflow-hidden">
            <div className="px-2 pb-4 text-[13px] leading-relaxed text-tx-secondary md:bg-sf-secondary md:px-6 md:py-5 md:text-base">
              {item.body}
            </div>
          </AccordionPrimitive.Content>
        </AccordionPrimitive.Item>
      ))}
    </AccordionPrimitive.Root>
  );
}

/* ---------- Popover, tooltip, select ---------- */

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;

export function PopoverContent({
  children,
  className,
  align = "start",
}: {
  children: ReactNode;
  className?: string;
  align?: "start" | "center" | "end";
}) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={8}
        className={cn(
          "z-50 w-80 rounded-2xl border border-st-secondary bg-white p-5 shadow-[0_12px_40px_-8px_#0000001f] outline-none",
          "data-[state=open]:animate-fade-in",
          className,
        )}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  );
}

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <TooltipPrimitive.Root delayDuration={150}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-xl bg-tx px-3 py-2 text-[13px] leading-snug text-white shadow-lg data-[state=delayed-open]:animate-fade-in"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

export function Select({
  value,
  onValueChange,
  options,
  label,
  className,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  label: string;
  className?: string;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        aria-label={label}
        className={cn(
          "inline-flex h-11 min-w-36 items-center justify-between gap-3 rounded-full border border-st bg-white pr-3 pl-4 text-caption font-medium text-tx-secondary transition-colors hover:border-grey-400 focus:border-indigo-300 focus:shadow-focus focus:outline-none",
          className,
        )}
      >
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-4 text-tx-tertiary" strokeWidth={1.5} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={6}
          className="z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-2xl border border-st-secondary bg-white p-1 shadow-[0_12px_40px_-8px_#0000001f]"
        >
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 text-caption text-tx outline-none select-none data-[highlighted]:bg-sf-secondary"
              >
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check className="size-4 text-indigo-700" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

/* ---------- Checkbox and slider ---------- */

export function Checkbox({
  checked,
  onCheckedChange,
  id,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
}) {
  return (
    <CheckboxPrimitive.Root
      id={id}
      checked={checked}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      className="grid size-5 shrink-0 place-items-center rounded-[4px] border-2 border-st bg-white transition-[border-color,transform,background-color] duration-[120ms] hover:border-grey-400 active:scale-90 data-[state=checked]:border-ink-app data-[state=checked]:bg-ink-app"
    >
      <CheckboxPrimitive.Indicator className="animate-[bloom_120ms_ease-out] text-white">
        <Check className="size-3.5" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export function Slider({
  value,
  onValueChange,
  min = 0,
  max = 1,
  step = 0.05,
  label,
}: {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label: string;
}) {
  return (
    <SliderPrimitive.Root
      value={[value]}
      min={min}
      max={max}
      step={step}
      onValueChange={([v]) => onValueChange(v)}
      aria-label={label}
      className="relative flex h-5 w-full touch-none items-center select-none"
    >
      <SliderPrimitive.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-sf-tertiary">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-indigo-600" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block size-5 rounded-full border border-st bg-white shadow-[0_1px_3px_#00000029] transition-transform hover:scale-110 focus-visible:outline-2 focus-visible:outline-indigo-600" />
    </SliderPrimitive.Root>
  );
}
