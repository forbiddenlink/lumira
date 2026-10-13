import { defineRailway, preserve, project, service } from "railway/iac";

// Replaces railway.toml (Config as Code, hard cutoff 2026-12-01).
// Lightweight gallery + cloud-generation deployment (no local ML / no GPU): the
// web app boots torch-free from Dockerfile.gallery and generation runs through
// the cloud Replicate/Magica APIs. Variables stay on Railway (preserve()); see
// docs/RAILWAY_ADMIN_SETUP.md for the full list.
export const partial = "lumira-gallery";

export default defineRailway(() => {
  const lumiraGallery = service("lumira-gallery", {
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile.gallery",
    },
    // No startCommand: the Dockerfile CMD handles it.
    healthcheck: "/health",
    healthcheckTimeout: 100,
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
    },
    replicas: { "us-west2": 1 },
    env: { ALLOWED_ORIGINS: preserve(), RAILWAY_API_KEY: preserve() },
  });

  return project("lumira-gallery", {
    resources: [lumiraGallery],
  });
});
