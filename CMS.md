# WLB CMS — AI Agent Guide

## What This Repo Is
ex
Laravel 10 + PHP 8.2 **Content Management System** for TV2Z, a video streaming platform.
This CMS is the **back-office** — operators use it to manage content, users, subscriptions, and configuration. Changes made here are consumed by the **API project** (separate repo) which serves end users.

## Knowledge Graph
`graph_cms/graph.json` — 8,402 nodes, 14,267 edges covering this codebase.

## When to Work in This Repo
Come here when the task involves:
- Admin UI changes (Livewire components, Blade views)
- Content/media management (videos, series, seasons, collections, live channels)
- User & subscription management
- Bundle & packaging configuration
- Role/permission changes
- Email templates or notifications
- Feature flags, zone validation, device configuration
- **Database schema changes** → add a migration under `database/migrations/`
- **Seed/reference data** → add a seeder under `database/seeders/`
- Background jobs, queues, encoding pipeline

## When to Go to the API Repo
Go to the API repo (not this one) when the task is:
- Changing what the mobile/web client receives
- Modifying API response shapes or endpoints
- Player or stream delivery logic

## Key Paths
| Area | Path |
|---|---|
| Models | `app/Models/` |
| Controllers | `app/Http/Controllers/` |
| Livewire components | `app/Livewire/` |
| Services | `app/Services/` |
| Jobs | `app/Jobs/` |
| **Migrations (SQL)** | `database/migrations/` |
| Seeders | `database/seeders/` |
| Routes (web) | `routes/web.php` |
| Routes (tenant) | `routes/tenant.php` |
| Views | `resources/views/` |
| Config | `config/` |

## SQL / Migration Work
- All schema changes live in `database/migrations/` (715+ existing files — check before adding)
- Multi-tenant: some migrations run per-tenant via `Stancl\Tenancy`; check existing patterns
- Run `php artisan migrate` (or tenant-aware equivalent) after adding migrations
- Seeders in `database/seeders/` for reference/config data

## Codebase Knowledge Graph
A pre-built knowledge graph of this repo is at `graphify-out/graph.json`.
Use it to:
- Find relationships between classes/files without reading everything
- Identify which community/cluster a file belongs to (`community` field)
- Trace method-to-method or file-to-file connections

## Stack Summary
- **Backend:** Laravel 10, PHP 8.2, Eloquent ORM
- **Frontend:** Livewire 3, Bootstrap 4, Webpack/Laravel Mix
- **Auth/Permissions:** Spatie Laravel-Permission
- **Multi-tenancy:** Stancl/Tenancy v3
- **Storage:** AWS S3, Azure Blob
- **Queue:** AWS SQS
- **CDN/Media:** Akamai, Brightcove
