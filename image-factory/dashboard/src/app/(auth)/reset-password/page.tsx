"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { toast } from "@/hooks/use-toast";

export default function ResetPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
      toast({ title: "Reset link sent", description: "Check your email for instructions" });
    } catch (err: any) {
      toast({ title: "Failed", description: err.message || "Please try again", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Reset password</CardTitle>
        <CardDescription>
          {sent ? "Check your email for the reset link" : "Enter your email to receive a reset link"}
        </CardDescription>
      </CardHeader>
      {!sent && (
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-4">
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Sending..." : "Send reset link"}
            </Button>
          </CardFooter>
        </form>
      )}
      <CardFooter className="justify-center">
        <Link href="/login" className="text-sm text-muted-foreground hover:text-primary">
          Back to sign in
        </Link>
      </CardFooter>
    </Card>
  );
}
