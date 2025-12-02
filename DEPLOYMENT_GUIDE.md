# Deployment Guide - Render

## 🚀 Deploy to Render (Free Tier)

### Prerequisites
- ✅ GitHub repository (already done!)
- ✅ Gemini API key (you have it in .env)
- ✅ Render account (sign up at https://render.com)

---

## Step-by-Step Deployment

### 1. Create Web Service on Render

Go to: https://dashboard.render.com/

Click: **"New +"** → **"Web Service"**

### 2. Connect GitHub Repository

- Select: **"Build and deploy from a Git repository"**
- Click: **"Connect GitHub"**
- Choose: `madhurishah3222/SmartMedicineManagementSystemUsingAI-OCR`

### 3. Configure Service

Fill in the form:

**Name**: `medicine-ocr` (or any name you like)

**Region**: `Oregon (US West)` or closest to you

**Branch**: `main`

**Root Directory**: Leave empty

**Runtime**: `Python 3`

**Build Command**:
```bash
pip install -r requirements.txt
```

**Start Command**:
```bash
gunicorn app:app
```

### 4. Add Environment Variables

Click **"Add Environment Variable"** for each:

| Name | Value |
|------|-------|
| `GEMINI_API_KEY` | `AIzaSyChcQ5QP4BD2s999xw3OuhPqC94e_Xu3n0` |
| `FLASK_ENV` | `production` |
| `PYTHON_VERSION` | `3.11.0` |

### 5. Select Plan

- Choose: **"Free"** (0$/month)
- Note: Free tier sleeps after 15 min of inactivity

### 6. Create Web Service

Click: **"Create Web Service"**

---

## ⏳ Deployment Process

### Build Phase (~5-10 minutes)
```
Cloning repository...
Installing Python 3.11...
Running: pip install -r requirements.txt
Installing Flask, Pillow, SQLAlchemy, google-generativeai...
Build complete!
```

### Deploy Phase (~1-2 minutes)
```
Starting: gunicorn app:app
Server running on port 10000
Deploy complete!
```

### Live! 🎉
```
Your service is live at:
https://medicine-ocr-xxxx.onrender.com
```

---

## 🔧 Post-Deployment Configuration

### 1. Test Your Deployment

Visit your Render URL:
```
https://your-app-name.onrender.com
```

You should see the Medicine OCR homepage!

### 2. Test Login

**Owner Account**:
- Username: `owner`
- Password: `owner123`

**User Account**:
- Username: `user`
- Password: `user123`

### 3. Test OCR

1. Login as Owner
2. Go to "Label" section
3. Upload a medicine strip image
4. Click "Scan Image"
5. Verify results

---

## 🐛 Troubleshooting

### Issue: Build Failed

**Check**:
- `requirements.txt` is in root directory
- All dependencies are listed
- Python version is 3.11

**Solution**:
```bash
# Add to requirements.txt if missing
Flask==3.0.3
gunicorn==21.2.0
Pillow==10.4.0
google-generativeai==0.7.2
```

### Issue: Application Error

**Check Logs**:
- Go to Render Dashboard
- Click on your service
- Click "Logs" tab
- Look for error messages

**Common Issues**:
1. Missing environment variable (GEMINI_API_KEY)
2. Database path issues
3. Port binding issues

**Solution**:
- Verify environment variables are set
- Check logs for specific errors

### Issue: 502 Bad Gateway

**Cause**: App not starting correctly

**Solution**:
1. Check Start Command is: `gunicorn app:app`
2. Verify `app.py` is in root directory
3. Check logs for startup errors

### Issue: Database Not Persisting

**Cause**: Render free tier doesn't persist files

**Solution**:
- Use Render PostgreSQL (free tier available)
- Or accept that database resets on each deploy (for demo purposes)

---

## 📊 Render Free Tier Limits

- ✅ 750 hours/month (enough for 1 app running 24/7)
- ✅ Automatic HTTPS
- ✅ Custom domains
- ⚠️ Sleeps after 15 min inactivity (wakes on request)
- ⚠️ No persistent disk (database resets on deploy)

---

## 🔄 Auto-Deploy from GitHub

Enable auto-deploy so your app updates when you push to GitHub:

1. Go to Render Dashboard
2. Click on your service
3. Go to "Settings"
4. Enable "Auto-Deploy"
5. Select branch: `main`

Now every `git push` will automatically deploy!

---

## 🌐 Custom Domain (Optional)

### Add Custom Domain

1. Go to Render Dashboard
2. Click on your service
3. Go to "Settings" → "Custom Domain"
4. Add your domain: `medicine-ocr.yourdomain.com`
5. Update DNS records as instructed

---

## 📈 Monitoring

### View Logs
```
Render Dashboard → Your Service → Logs
```

### View Metrics
```
Render Dashboard → Your Service → Metrics
```

Shows:
- CPU usage
- Memory usage
- Request count
- Response times

---

## 🔐 Security Best Practices

### 1. Environment Variables
- ✅ Never commit API keys to GitHub
- ✅ Use Render's environment variables
- ✅ Rotate keys regularly

### 2. HTTPS
- ✅ Render provides automatic HTTPS
- ✅ All traffic is encrypted

### 3. Database
- ⚠️ SQLite resets on deploy (free tier)
- ✅ Use PostgreSQL for production
- ✅ Regular backups

---

## 🚀 Upgrade to Paid Plan (Optional)

### Starter Plan ($7/month)
- ✅ No sleep
- ✅ Persistent disk
- ✅ More resources
- ✅ Priority support

### Professional Plan ($25/month)
- ✅ All Starter features
- ✅ More CPU/RAM
- ✅ Horizontal scaling
- ✅ Advanced metrics

---

## 📝 Deployment Checklist

Before deploying:
- [ ] GitHub repository is public or connected to Render
- [ ] `requirements.txt` is up to date
- [ ] `Procfile` exists (optional, Render uses Start Command)
- [ ] `runtime.txt` specifies Python version
- [ ] `.gitignore` excludes `.env` and sensitive files
- [ ] Environment variables are ready (GEMINI_API_KEY)
- [ ] Tested locally with `gunicorn app:app`

After deploying:
- [ ] Service builds successfully
- [ ] Service starts without errors
- [ ] Homepage loads
- [ ] Login works (owner and user)
- [ ] OCR functionality works
- [ ] Database operations work
- [ ] No errors in logs

---

## 🎉 Success!

Your Medicine OCR app is now live and accessible worldwide!

**Share your URL**:
```
https://your-app-name.onrender.com
```

**Monitor your app**:
```
https://dashboard.render.com
```

---

## 📞 Support

**Render Documentation**: https://render.com/docs

**Render Community**: https://community.render.com

**Your GitHub Repo**: https://github.com/madhurishah3222/SmartMedicineManagementSystemUsingAI-OCR

---

**Deployment Time**: ~10-15 minutes  
**Cost**: Free (with limitations)  
**Difficulty**: Easy ⭐⭐☆☆☆
