# API V1

## Optimisation

`POST /v1/optimizations`

En-tête obligatoire: `X-API-Key`.

### Requête minimale

```json
{
  "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer", "max_vehicles": 5},
  "budget_seconds": 30,
  "seed": 1,
  "items": [
    {
      "id": "PAL-001",
      "quantity": 2,
      "shape": "pallet",
      "length": 1200,
      "width": 800,
      "height": 1400,
      "weight": 500,
      "destination": "Client A",
      "delivery_order": 2,
      "rotation_allowed": true
    }
  ]
}
```

Unités par défaut: millimètres et kilogrammes. Les unités `cm`, `m`, `g` et `t` sont acceptées. La quantité est développée avant la limite de 100 objets.

La réponse contient un statut explicite, `time_limit_reached`, `optimality_guaranteed=false`, une solution pour l’API publique, ses métriques, ses véhicules, ses placements et les diagnostics.

## Catalogue véhicules de l’interface

Ces routes utilisent `X-Tenant-ID` et, hors mode démonstration, la clé API associée:

- `GET /api/vehicles`: liste du catalogue de l’entreprise;
- `POST /api/vehicles`: création ou mise à jour d’un véhicule;
- `DELETE /api/vehicles/{model_id}`: suppression;
- `POST /api/vehicles/reset-defaults`: restauration des modèles de démonstration.

Champs principaux d’un véhicule:

```json
{
  "model_id": "semi_trailer",
  "name": "Semi-remorque",
  "interior_length_mm": 13600,
  "interior_width_mm": 2450,
  "interior_height_mm": 2700,
  "linear_meter_width_mm": 2400,
  "payload_kg": 24000,
  "door_width_mm": 2450,
  "door_height_mm": 2700
}
```

Une mise à jour modifiant réellement les valeurs incrémente la version. Le plan retourné conserve l’identifiant `model_id@version` employé lors du calcul.
