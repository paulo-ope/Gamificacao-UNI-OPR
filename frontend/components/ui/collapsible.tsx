"use client";

import * as React from "react";

type CollapsibleContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
};

const CollapsibleContext = React.createContext<CollapsibleContextValue | null>(null);

type CollapsibleProps = React.HTMLAttributes<HTMLDivElement> & {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const Collapsible = React.forwardRef<HTMLDivElement, CollapsibleProps>(function Collapsible(
  { open, defaultOpen = false, onOpenChange, children, ...props },
  ref
) {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen);
  const currentOpen = open ?? internalOpen;

  function setOpen(nextOpen: boolean) {
    if (open === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  }

  return (
    <CollapsibleContext.Provider value={{ open: currentOpen, setOpen }}>
      <div ref={ref} data-state={currentOpen ? "open" : "closed"} {...props}>
        {children}
      </div>
    </CollapsibleContext.Provider>
  );
});

function CollapsibleTrigger({
  children,
  asChild = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }) {
  const context = React.useContext(CollapsibleContext);
  if (!context) return null;
  const triggerProps = {
    "aria-expanded": context.open,
    onClick: () => context.setOpen(!context.open),
    ...props
  };

  // React.Children.only só pode ser chamado quando de fato vamos clonar um único filho (asChild).
  // Chamá-lo incondicionalmente quebrava todo trigger com mais de um filho (ex.: texto + ícone) -
  // achado real: toda abertura do drawer de auditoria (label + ChevronDown) travava a tela inteira.
  if (asChild) {
    const child = React.Children.only(children) as React.ReactElement;
    return React.cloneElement(child, triggerProps);
  }
  return (
    <button type="button" {...triggerProps}>
      {children}
    </button>
  );
}

function CollapsibleContent({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const context = React.useContext(CollapsibleContext);
  if (!context?.open) return null;
  return <div {...props}>{children}</div>;
}

export { Collapsible, CollapsibleContent, CollapsibleTrigger };
