import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";
type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary"|"secondary"|"danger"|"ghost" };
export const Button = forwardRef<HTMLButtonElement,Props>(({className,variant="primary",...props},ref)=><button ref={ref} className={cn("ui-button",`ui-button--${variant}`,className)} {...props}/>);
Button.displayName="Button";
