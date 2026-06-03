"use client";

import { Info } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useId, useMemo, useRef, useState } from "react";

type InfoHintProps = {
  ariaLabel: string;
  description: string;
  side?: "top" | "right" | "bottom" | "left";
  title?: string;
};

const popupClasses: Record<NonNullable<InfoHintProps["side"]>, string> = {
  top: "-translate-x-1/2 -translate-y-full",
  right: "translate-y-[-50%]",
  bottom: "-translate-x-1/2",
  left: "-translate-x-full translate-y-[-50%]"
};

export function InfoHint({ ariaLabel, description, side = "top", title }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const containerRef = useRef<HTMLSpanElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popupRef = useRef<HTMLSpanElement | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hintId = useId();

  useEffect(() => {
    setMounted(true);
    return () => {
      setMounted(false);
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;

      const gap = 10;
      if (side === "top") {
        setPosition({ left: rect.left + rect.width / 2, top: rect.top - gap });
      } else if (side === "right") {
        setPosition({ left: rect.right + gap, top: rect.top + rect.height / 2 });
      } else if (side === "bottom") {
        setPosition({ left: rect.left + rect.width / 2, top: rect.bottom + gap });
      } else {
        setPosition({ left: rect.left - gap, top: rect.top + rect.height / 2 });
      }
    };

    const handlePointer = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (!containerRef.current?.contains(target) && !popupRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };

    updatePosition();
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);
    document.addEventListener("keydown", handleKey);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKey);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, side]);

  const clearCloseTimer = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => {
      setOpen(false);
    }, 120);
  };

  const popupClassName = useMemo(
    () =>
      `fixed z-[120] w-64 rounded-2xl border border-slate-200 bg-white/98 p-3 text-left shadow-[0_18px_40px_-24px_rgba(15,23,42,0.4)] backdrop-blur ${popupClasses[side]}`,
    [side]
  );

  return (
    <span
      ref={containerRef}
      className="relative inline-flex shrink-0"
      onMouseEnter={() => {
        clearCloseTimer();
        setOpen(true);
      }}
      onMouseLeave={scheduleClose}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-label={ariaLabel}
        aria-describedby={open ? hintId : undefined}
        aria-expanded={open}
        onFocus={() => {
          clearCloseTimer();
          setOpen(true);
        }}
        onBlur={(event) => {
          const nextTarget = event.relatedTarget as Node | null;
          if (!containerRef.current?.contains(nextTarget) && !popupRef.current?.contains(nextTarget)) {
            setOpen(false);
          }
        }}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-slate-400 transition hover:border-slate-300 hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2"
      >
        <Info className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
      {open && mounted
        ? createPortal(
            <span
              ref={popupRef}
              id={hintId}
              role="tooltip"
              className={popupClassName}
              style={{ left: position.left, top: position.top }}
              onMouseEnter={() => {
                clearCloseTimer();
                setOpen(true);
              }}
              onMouseLeave={scheduleClose}
            >
              {title ? <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</span> : null}
              <span className={`block text-sm leading-5 text-slate-700 ${title ? "mt-1.5" : ""}`}>{description}</span>
            </span>,
            document.body
          )
        : null}
    </span>
  );
}
