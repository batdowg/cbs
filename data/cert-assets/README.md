# Certificate asset persistence

This directory persists certificate templates and badge images on the host. Copy the current contents of `app/assets/` here when provisioning or refreshing an environment, e.g.

```
cp -a app/assets/. data/cert-assets/
```

The directory is bind-mounted into the app container at `/app/app/assets` so templates remain available across rebuilds. Keep the host copy backed up because uploaded templates and badges live here.
