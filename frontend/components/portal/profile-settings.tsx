"use client";

import { Camera, Check, ImageUp, Loader2, Mail, Phone, Trash2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { PortalProfile } from "@/lib/types";

function initials(name: string) {
  return name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export function ProfileSettings() {
  const inputRef = useRef<HTMLInputElement>(null);
  const photoUrlRef = useRef<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const [profile, setProfile] = useState<PortalProfile | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [pendingPhoto, setPendingPhoto] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [isDraggingPhoto, setIsDraggingPhoto] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    async function loadProfile() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.portalProfile();
        if (!isActive) return;
        setProfile(data);
        setPhone(data.phone ?? "");
        setEmail(data.email ?? "");
        if (data.has_photo) {
          const photo = await api.portalProfilePhoto();
          const objectUrl = URL.createObjectURL(photo);
          if (isActive) {
            photoUrlRef.current = objectUrl;
            setPhotoUrl(objectUrl);
          } else {
            URL.revokeObjectURL(objectUrl);
          }
        }
      } catch (err) {
        if (isActive) setError(err instanceof Error ? err.message : "Não foi possível carregar seu perfil.");
      } finally {
        if (isActive) setLoading(false);
      }
    }

    loadProfile();
    return () => {
      isActive = false;
      if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  function clearPendingPhoto() {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setPreviewUrl(null);
    setPendingPhoto(null);
  }

  function queuePhoto(file: File) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setError('Use uma imagem JPEG, PNG ou WEBP de até 2MB.');
      return;
    }
    clearPendingPhoto();
    const objectUrl = URL.createObjectURL(file);
    previewUrlRef.current = objectUrl;
    setPreviewUrl(objectUrl);
    setPendingPhoto(file);
    setError(null);
    setNotice(null);
  }

  async function handleSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.updatePortalProfile({ phone: phone.trim() || null, email: email.trim() || null });
      setProfile(updated);
      setNotice("Dados de contato atualizados.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar seus dados.");
    } finally {
      setSaving(false);
    }
  }

  async function handlePhotoChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) queuePhoto(file);
  }

  async function handleUploadPhoto() {
    if (!pendingPhoto) return;
    setPhotoLoading(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.uploadPortalProfilePhoto(pendingPhoto);
      const photo = await api.portalProfilePhoto();
      if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current);
      const objectUrl = URL.createObjectURL(photo);
      photoUrlRef.current = objectUrl;
      setPhotoUrl(objectUrl);
      setProfile(updated);
      clearPendingPhoto();
      setNotice("Foto de perfil atualizada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar a foto.");
    } finally {
      setPhotoLoading(false);
    }
  }

  async function handleRemovePhoto() {
    if (!window.confirm("Remover sua foto de perfil?")) return;
    setPhotoLoading(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.deletePortalProfilePhoto();
      if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current);
      photoUrlRef.current = null;
      setPhotoUrl(null);
      setProfile(updated);
      setNotice("Foto de perfil removida.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível remover a foto.");
    } finally {
      setPhotoLoading(false);
    }
  }

  if (loading) return <section className="rounded-lg border bg-white p-5 text-sm text-slate-600">Carregando perfil...</section>;
  if (!profile) return <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{error ?? "Seu perfil não está disponível."}</section>;

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-slate-500">Minha conta</p>
          <h2 className="mt-1 text-xl font-semibold sm:text-2xl">Perfil e contato</h2>
        </div>
        <Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]">Cadastro da Gamificação</Badge>
      </div>

      {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
      {notice ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p> : null}

      <section className="grid overflow-hidden rounded-lg border bg-white md:grid-cols-[280px_1fr]">
        <div className="uni-gradient flex flex-col items-center justify-center p-6 text-center text-white">
          <div className="flex h-28 w-28 items-center justify-center overflow-hidden rounded-full border-4 border-white/35 bg-white/15 text-3xl font-semibold">
            {photoUrl ? <img alt={`Foto de ${profile.name}`} className="h-full w-full object-cover" src={photoUrl} /> : initials(profile.name)}
          </div>
          <p className="mt-4 text-lg font-semibold">{profile.name}</p>
          <p className="mt-1 text-sm text-white/80">{profile.role}</p>
          <p className="mt-4 text-xs text-white/75">{photoUrl ? "Foto de perfil atual" : "Sem foto cadastrada"}</p>
          {photoUrl ? <Button aria-label="Remover foto" className="mt-3 border-white/40 bg-white/10 text-white hover:bg-white/20" disabled={photoLoading} size="icon" variant="outline" onClick={handleRemovePhoto}><Trash2 className="h-4 w-4" /></Button> : null}
        </div>

        <form className="space-y-5 p-5 sm:p-6" onSubmit={handleSave}>
          <input ref={inputRef} accept="image/jpeg,image/png,image/webp" className="hidden" type="file" onChange={handlePhotoChange} />
          <div
            className={`rounded-lg border-2 border-dashed p-4 transition-colors ${isDraggingPhoto ? "border-[#27d9bf] bg-[#27d9bf]/10" : "border-slate-200 bg-slate-50"}`}
            onDragEnter={(event) => { event.preventDefault(); setIsDraggingPhoto(true); }}
            onDragLeave={(event) => { event.preventDefault(); setIsDraggingPhoto(false); }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); setIsDraggingPhoto(false); const file = event.dataTransfer.files?.[0]; if (file) queuePhoto(file); }}
          >
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#2d5fff]/10 text-[#0028f3]"><ImageUp className="h-5 w-5" /></div>
              <div className="min-w-0 flex-1"><p className="text-sm font-medium text-slate-950">Atualizar foto de perfil</p><p className="text-xs text-slate-500">JPEG, PNG ou WEBP, até 2MB</p></div>
              <Button disabled={photoLoading} type="button" variant="outline" onClick={() => inputRef.current?.click()}><Upload className="h-4 w-4" />Selecionar foto</Button>
            </div>
          </div>

          {pendingPhoto && previewUrl ? (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[#2d5fff]/20 bg-[#2d5fff]/5 p-3">
              <img alt="Prévia da nova foto" className="h-14 w-14 rounded-full object-cover" src={previewUrl} />
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{pendingPhoto.name}</p><p className="text-xs text-slate-500">{(pendingPhoto.size / 1024 / 1024).toFixed(1)} MB · pronta para atualizar</p></div>
              <Button aria-label="Cancelar nova foto" disabled={photoLoading} size="icon" type="button" variant="ghost" onClick={clearPendingPhoto}><X className="h-4 w-4" /></Button>
              <Button disabled={photoLoading} type="button" onClick={handleUploadPhoto}>{photoLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}Confirmar foto</Button>
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div><Label>Regional</Label><p className="mt-2 text-sm font-medium text-slate-950">{profile.regional}</p></div>
            <div><Label>Cargo</Label><p className="mt-2 text-sm font-medium text-slate-950">{profile.role}</p></div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="profile-phone">Telefone</Label><div className="relative"><Phone className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><Input className="pl-9" id="profile-phone" inputMode="tel" placeholder="(00) 00000-0000" value={phone} onChange={(event) => setPhone(event.target.value)} /></div></div>
            <div className="space-y-2"><Label htmlFor="profile-email">E-mail de contato</Label><div className="relative"><Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><Input className="pl-9" id="profile-email" inputMode="email" placeholder="voce@exemplo.com" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div></div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4"><p className="text-xs text-slate-500">Regional, cargo e acesso são atualizados pela gestão.</p><Button disabled={saving} type="submit">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}Salvar contato</Button></div>
        </form>
      </section>
    </section>
  );
}
