# CarbonTrack Render Deployment

This deployment package preserves the existing React + Flask application and builds the frontend into `backend/static` inside the Docker image.

## Deploy with Render Blueprint

1. Extract this ZIP.
2. Create a new GitHub repository and upload the extracted project contents. Keep `.gitignore` enabled; do not upload `backend/.env`.
3. In Render, choose **New + → Blueprint** and connect the GitHub repository containing `render.yaml`.
4. Review the Blueprint and create the resources. It defines a Docker web service and a PostgreSQL database.
5. In the Render web service's Environment settings, add the required integrations below before testing those features.
6. Wait for the deploy to finish. Check `https://YOUR-SERVICE.onrender.com/api/health` and `/api/ready`.
7. Open the website and test login, registration, dashboards, trips, reports, and maps.

## Environment variables to add in Render

Set these only if you use the corresponding feature:
- `GOOGLE_MAPS_API_KEY`: browser Maps JavaScript key returned by the existing config endpoint. Restrict it to your Render domain by HTTP referrer and enable the required Maps JavaScript API.
- `GOOGLE_ROUTES_API_KEY`: server-side Google Routes API key.
- `GOOGLE_PLACES_API_KEY`: server-side Places API key.
- `OPENWEATHER_API_KEY`: OpenWeather key.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: SMTP configuration for real email OTP delivery.
- `AADHAAR_ENCRYPTION_KEY`: only if required by your app's Aadhaar encryption code; generate a Fernet key and keep it stable once encrypted records exist.

The Blueprint generates `SECRET_KEY` and `JWT_SECRET_KEY`. Do not replace them casually after users have logged in, because doing so invalidates existing tokens.

## Database seeding

On startup, the entrypoint runs `flask --app app db upgrade` and then `python seed.py`. The seed script has been changed to **seed only when the database is empty**; it no longer drops existing production tables or user data. It uses the CSVs already present in `backend/data/`, including the admins, drivers, vehicles, trips, and AI prediction rows.

Sample seed credentials documented in the source project:
- Admin usernames `admin1` through `admin5`, password `Admin@123`.
- Driver usernames `driver1` through `driver500`, password `Driver@123`; only approved drivers can log in.

These are public demo credentials. Change or disable them immediately after first login before exposing the site to the public.

## Important limitations to know

- The free Render web service can sleep when idle and cold-start slowly.
- Free database availability, retention, and expiration policies can change. Check Render's current database plan details before relying on it for permanent data. Back up important data.
- Files saved to the container filesystem (such as uploaded registration documents) are not durable across rebuilds/redeploys on ephemeral hosting. Persistent uploads need a persistent disk (where supported) or object storage.
- Real Google Maps/Routes/Places, weather, and email OTP features will not work until valid API credentials are configured and their required APIs/billing/restrictions are correct.
- This package is deployment-configured, but a live Render deploy and external API checks must still be performed in your Render account.

## Local development

Keep your local `.env` on your machine. Use `.env.example` as a template; never commit `.env`.
