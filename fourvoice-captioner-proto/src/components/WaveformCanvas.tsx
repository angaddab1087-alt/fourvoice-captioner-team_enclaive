import React, { useEffect, useRef } from "react";

interface WaveformCanvasProps {
  speed?: number;
  amplitudeMultiplier?: number;
  color?: string;
  isPulsing?: boolean;
}

export const WaveformCanvas: React.FC<WaveformCanvasProps> = ({
  speed = 1.0,
  amplitudeMultiplier = 1.0,
  color = "rgba(240, 169, 62, 0.4)", // brand-amber
  isPulsing = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId: number;
    let phase = 0;

    const resizeCanvas = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      canvas.width = rect?.width || window.innerWidth;
      canvas.height = rect?.height || 300;
    };

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    // Create a resize observer to watch the parent container specifically
    const resizeObserver = new ResizeObserver(() => {
      resizeCanvas();
    });
    if (canvas.parentElement) {
      resizeObserver.observe(canvas.parentElement);
    }

    const draw = () => {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;

      // Pulse multiplier for breathing effect
      const pulse = isPulsing ? 1.0 + 0.15 * Math.sin(phase * 1.5) : 1.0;

      // Draw three layered waves
      const waves = [
        { frequency: 0.005, amplitude: 50 * amplitudeMultiplier * pulse, speed: 0.04 * speed, color: color },
        { frequency: 0.012, amplitude: 25 * amplitudeMultiplier * pulse, speed: -0.06 * speed, color: "rgba(95, 191, 140, 0.3)" }, // brand-mint
        { frequency: 0.003, amplitude: 35 * amplitudeMultiplier * pulse, speed: 0.02 * speed, color: "rgba(237, 233, 224, 0.1)" }, // bone white
      ];

      waves.forEach((wave) => {
        ctx.beginPath();
        ctx.strokeStyle = wave.color;
        ctx.lineWidth = 1.5;

        for (let x = 0; x < width; x += 5) {
          // Dynamic y position based on trigonometric sine function waves
          const y =
            centerY +
            Math.sin(x * wave.frequency + phase * (wave.speed > 0 ? 1 : -1) * Math.abs(wave.speed)) *
              wave.amplitude *
              Math.sin((x / width) * Math.PI); // Pin the ends to zero for a professional look

          if (x === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
      });

      // Update Phase
      phase += 0.5 * speed;
      animationId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resizeCanvas);
      resizeObserver.disconnect();
    };
  }, [speed, amplitudeMultiplier, color, isPulsing]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none opacity-40 mix-blend-screen"
      style={{ filter: "blur(0.5px)" }}
    />
  );
};
