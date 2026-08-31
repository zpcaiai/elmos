"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const maximumRecordingSeconds = 10 * 60;
const maximumRecordingSamples = 32 * 1024 * 1024 - 22;

function encodeWaveFile(chunks: Float32Array[], sampleRate: number): Blob {
  const samples = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + samples * 2, true); text(8, "WAVE"); text(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, samples * 2, true);
  let offset = 44;
  for (const chunk of chunks) {
    for (const value of chunk) {
      const bounded = Math.max(-1, Math.min(1, value));
      view.setInt16(offset, bounded < 0 ? bounded * 0x8000 : bounded * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export function useMicrophoneRecorder(onRecorded: (file: File) => void) {
  const [recording, setRecording] = useState(false);
  const [permission, setPermission] = useState<"PROMPT" | "GRANTED" | "DENIED" | "UNAVAILABLE">("PROMPT");
  const cleanup = useRef<((commit: boolean) => void) | null>(null);
  const generation = useRef(0);
  const startingOwner = useRef<number | null>(null);

  const stop = useCallback(() => cleanup.current?.(true), []);
  const cancel = useCallback(() => {
    generation.current += 1;
    startingOwner.current = null;
    cleanup.current?.(false);
    setRecording(false);
  }, []);
  const start = useCallback(async () => {
    if (recording || startingOwner.current !== null) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setPermission("UNAVAILABLE");
      return;
    }
    const requestOwner = generation.current + 1;
    generation.current = requestOwner;
    startingOwner.current = requestOwner;
    let stream: MediaStream | undefined;
    try {
      const activeStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true }, video: false });
      stream = activeStream;
      if (generation.current !== requestOwner) {
        activeStream.getTracks().forEach((track) => track.stop());
        return;
      }
      setPermission("GRANTED");
      const AudioContextClass = window.AudioContext;
      const context = new AudioContextClass();
      const source = context.createMediaStreamSource(activeStream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      let sampleCount = 0;
      let timeout = 0;
      let finished = false;
      const finish = (commit: boolean) => {
        if (finished) return;
        finished = true;
        if (cleanup.current === finish) cleanup.current = null;
        window.clearTimeout(timeout);
        processor.disconnect();
        source.disconnect();
        activeStream.getTracks().forEach((track) => track.stop());
        const sampleRate = context.sampleRate;
        void context.close();
        setRecording(false);
        if (commit && generation.current === requestOwner && chunks.length > 0) {
          const blob = encodeWaveFile(chunks, sampleRate);
          onRecorded(new File([blob], `microphone-${Date.now()}.wav`, {
            type: "audio/wav",
            lastModified: Date.now(),
          }));
        }
      };
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        const remaining = maximumRecordingSamples - sampleCount;
        if (remaining <= 0) {
          finish(true);
          return;
        }
        const chunk = new Float32Array(input.subarray(0, Math.min(input.length, remaining)));
        chunks.push(chunk);
        sampleCount += chunk.length;
        if (sampleCount >= maximumRecordingSamples) finish(true);
      };
      source.connect(processor);
      processor.connect(context.destination);
      timeout = window.setTimeout(() => finish(true), maximumRecordingSeconds * 1000);
      cleanup.current = finish;
      setRecording(true);
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (generation.current === requestOwner) {
        setPermission(error instanceof DOMException && error.name === "NotAllowedError" ? "DENIED" : "UNAVAILABLE");
        setRecording(false);
      }
    } finally {
      if (startingOwner.current === requestOwner) startingOwner.current = null;
    }
  }, [onRecorded, recording]);

  useEffect(() => () => {
    generation.current += 1;
    cleanup.current?.(false);
  }, []);
  return { recording, permission, start, stop, cancel };
}
