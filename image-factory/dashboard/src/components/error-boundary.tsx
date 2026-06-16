"use client";

import React, { ReactNode, ReactElement } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Error caught by boundary:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render(): ReactElement {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-background">
          <div className="max-w-md mx-auto p-6 border rounded-lg bg-card">
            <div className="flex items-start gap-4">
              <AlertCircle className="h-6 w-6 text-destructive mt-1 shrink-0" />
              <div className="flex-1">
                <h2 className="font-semibold text-lg mb-2">Something went wrong</h2>
                <p className="text-sm text-muted-foreground mb-4">
                  {this.state.error?.message || "An unexpected error occurred."}
                </p>
                <Button
                  onClick={this.handleReset}
                  className="gap-2"
                  size="sm"
                >
                  <RefreshCw className="h-4 w-4" />
                  Try again
                </Button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return <>{this.props.children}</>;
  }
}
