import { useDeferredValue, useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, ArrowLeft, ArrowRight, Check, Heart, Menu, MessageCircle, Search, Send, ShoppingBag, X } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type User = { id: number; first_name: string; last_name: string; name: string; email: string; created_at: string }

type Stock = { size: string; quantity: number }
type Product = {
  product_id: string
  name: string
  garment_type: string
  description: string
  colors: string[]
  search_tags: string[]
  image_url: string
  price: number
  sizes: Stock[]
}
type ChatMessage = { role: 'user' | 'assistant'; text: string; products?: Product[] }
type ChatHistoryPayload = { authenticated: boolean; messages: Array<{ role: 'user' | 'assistant'; content: string; products?: Product[] }> }

const money = (price: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(price)
const imageSource = (path: string) => `${API_URL}${path}`
const excerpt = (text: string) => text.length > 104 ? `${text.slice(0, 101).trimEnd()}...` : text
const normalizeSearchText = (value: string) => value
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, ' ')
  .trim()

function useProducts() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_URL}/api/products`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('The product catalogue could not be reached.')
        return response.json() as Promise<Product[]>
      })
      .then(setProducts)
      .catch((fetchError: unknown) => {
        if (fetchError instanceof Error && fetchError.name !== 'AbortError') setError(fetchError.message)
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  return { products, loading, error }
}

function App() {
  const { products, loading, error } = useProducts()
  const [account, setAccount] = useState<User | null>(null)
  const [bagCount, setBagCount] = useState(0)
  const [chatOpen, setChatOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    let active = true
    fetch(`${API_URL}/api/auth/me`, { credentials: 'include' })
      .then((response) => response.ok ? response.json() as Promise<User> : null)
      .then((user) => { if (active && user) setAccount(user) })
      .catch(() => undefined)
    return () => { active = false }
  }, [])

  async function logout() {
    try {
      await fetch(`${API_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' })
    } finally {
      setAccount(null)
    }
  }

  return (
    <div className="site-shell">
      <div className="announcement"><span>NEW HAVEN, CT</span><span>Good things, for your Yale days and the long way home</span><span>EST. 2026</span></div>
      <header className="site-header">
        <button className="icon-button menu-toggle" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} aria-label="Toggle navigation"><Menu size={20} /></button>
        <Link className="wordmark" to="/" aria-label="Campus Customs home"><span className="wordmark-mark">CC</span><span>CAMPUS<br />CUSTOMS</span></Link>
        <nav className={`main-nav ${mobileMenuOpen ? 'is-open' : ''}`} aria-label="Main navigation">
          <NavLink to="/" end onClick={() => setMobileMenuOpen(false)}>Home</NavLink>
          <NavLink to="/products" onClick={() => setMobileMenuOpen(false)}>Products</NavLink>
          <NavLink to="/about" onClick={() => setMobileMenuOpen(false)}>About us</NavLink>
          {account ? <><span className="account-greeting">Hello, {account.first_name}</span><button className="logout-link" onClick={() => { setMobileMenuOpen(false); void logout() }}>Log out</button></> : <><NavLink to="/login" onClick={() => setMobileMenuOpen(false)}>Log in</NavLink><NavLink className="create-link" to="/create-account" onClick={() => setMobileMenuOpen(false)}>Create account <ArrowRight size={15} /></NavLink></>}
        </nav>
        <Link className="bag-link" to="/products" aria-label={`Shopping bag, ${bagCount} items`}><ShoppingBag size={19} /><span>Bag{bagCount > 0 && <b>{bagCount}</b>}</span></Link>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<HomePage products={products} loading={loading} error={error} />} />
          <Route path="/products" element={<ProductsPage products={products} loading={loading} error={error} />} />
          <Route path="/products/:productId" element={<ProductPage products={products} loading={loading} onAdd={() => setBagCount((count) => count + 1)} />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/login" element={<AccountPage mode="login" onAuthenticated={setAccount} />} />
          <Route path="/create-account" element={<AccountPage mode="create" onAuthenticated={setAccount} />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <div className="footer-top"><Link className="wordmark footer-wordmark" to="/"><span className="wordmark-mark">CC</span><span>CAMPUS<br />CUSTOMS</span></Link><p>For the quad, the court, the mountain<br />and every Sunday in between.</p><Link className="text-link light-link" to="/products">Find your thing <ArrowRight size={15} /></Link></div>
        <div className="footer-bottom"><span>New Haven, Connecticut</span><span>Made for the in-between.</span><span>© Campus Customs 2026</span></div>
      </footer>

      <ChatWidget isOpen={chatOpen} userId={account?.id ?? null} onToggle={() => setChatOpen(!chatOpen)} />
    </div>
  )
}

function HomePage({ products, loading, error }: { products: Product[]; loading: boolean; error: string }) {
  const featured = products.find((product) => product.product_id === 'basic-hoodie-big-yale') ?? products[0]
  const [promoOpen, setPromoOpen] = useState(false)

  useEffect(() => {
    if (sessionStorage.getItem('campus-customs-spooky-promo-dismissed')) return
    const timer = window.setTimeout(() => setPromoOpen(true), 1800)
    return () => window.clearTimeout(timer)
  }, [])

  function dismissPromo() {
    sessionStorage.setItem('campus-customs-spooky-promo-dismissed', 'true')
    setPromoOpen(false)
  }

  return (
    <>
      <section className="hero-section">
        <div className="hero-noir-backdrop" aria-hidden="true"><span className="noir-moon" /><span className="noir-haze haze-one" /><span className="noir-haze haze-two" /><span className="noir-grain" /><span className="spiderweb web-upper" /><span className="spiderweb web-lower" /></div>
        <div className="hero-copy">
          <p className="eyebrow"><span className="eyebrow-dot" /> AFTER DARK AT YALE · THE HALLOWEEN EDIT</p>
          <h1>Night falls.<br /><em>Bulldogs rise.</em></h1>
          <p className="hero-description">A little campus spirit for the long walk home, the late-night screening, and every New England night that arrives before you’re ready.</p>
          <div className="hero-actions"><Link className="button button-dark" to="/products">Shop the Halloween edit <ArrowRight size={16} /></Link><Link className="text-link" to="/about">Our New Haven story <ArrowDown size={15} /></Link></div>
          <div className="hero-note"><span>CC / 31.10</span><span>Official campus favorites · New Haven</span><span className="hero-rule" /></div>
        </div>
        <div className="hero-image-wrap">
          <div className="noir-scene-label"><span>SCENE 01</span><span>NEW HAVEN, 11:47 PM</span></div>
          {featured && <Link to={`/products/${featured.product_id}`} className="hero-image-link"><span className="noir-light-beam" aria-hidden="true" /><img src={imageSource(featured.image_url)} alt={featured.name} /><span className="image-caption">THE NIGHT-SHIFT CLASSIC <ArrowUpRightIcon /></span></Link>}
          {!featured && <div className="image-placeholder"><span>CC</span></div>}
          <div className="hero-stamp"><span>OFFICIAL</span><strong>YALE<br />AFTER DARK</strong><span>HALLOWEEN / CC</span></div>
          <span className="hero-image-index">A CAMPUS CUSTOMS NIGHT FILM · NO. 01</span>
        </div>
      </section>

      <section className="intro-strip"><span>THE NIGHT-SHIFT UNIFORM</span><p>From one last lap around campus to the first frost on the quad.</p><Link to="/products" aria-label="Browse products"><ArrowRight size={19} /></Link></section>

      <section className="featured-section section-pad">
        <div className="section-heading"><div><p className="eyebrow">A FEW CURRENT FAVORITES</p><h2>Good form, <em>all season.</em></h2></div><Link className="text-link" to="/products">Shop everything <ArrowRight size={15} /></Link></div>
        <ProductGrid products={products.slice(0, 4)} loading={loading} error={error} />
      </section>

      <section className="weekend-section">
        <div className="weekend-visual"><div className="weekend-frame"><span>THE NEW ENGLAND<br />WEEKEND, WELL PACKED</span><strong>From court<br />to chairlift.</strong><div className="weekend-scribble">SQUASH / SKI / REPEAT</div></div></div>
        <div className="weekend-copy"><p className="eyebrow">THE WEEKEND BAG</p><h2>One foot in<br />New Haven.<br /><em>One out of office.</em></h2><p>A warm-up before the match. A second layer for the ferry. A sweatshirt that knows the difference between a study break and a snow day.</p><Link className="button button-outline" to="/products">Meet your next layer <ArrowRight size={16} /></Link></div>
      </section>

      <section className="note-section"><p className="eyebrow">A SMALL INVITATION</p><h2>Wear it like you<br /><em>belong here.</em></h2><Link className="button button-dark" to="/about">Our New Haven story <ArrowRight size={16} /></Link></section>
      {promoOpen && <SpookyPricePromo onClose={dismissPromo} />}
    </>
  )
}

function SpookyPricePromo({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <div className="spooky-promo-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="spooky-promo" role="dialog" aria-modal="true" aria-labelledby="spooky-promo-title">
        <button className="spooky-promo-close" onClick={onClose} aria-label="Close promotion"><X size={18} /></button>
        <p className="eyebrow">A CAMPUS CUSTOMS HALLOWEEN NOTE</p>
        <h2 id="spooky-promo-title">Spooky good<br /><em>prices.</em></h2>
        <p>Explore the real-deal campus collection. No tricks, no made-up markdowns, just good Yale gear for the season.</p>
        <Link className="button button-dark" to="/products" onClick={onClose}>Browse the collection <ArrowRight size={16} /></Link>
        <span className="promo-footnote">Official campus favorites · New Haven</span>
      </section>
    </div>
  )
}

function ProductsPage({ products, loading, error }: { products: Product[]; loading: boolean; error: string }) {
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [category, setCategory] = useState('Everything')
  const deferredSearch = useDeferredValue(appliedSearch)
  const categories = ['Everything', 'T-shirts', 'Jackets', 'Hoodies', 'Sweaters & Sweatshirts']
  const categoryCounts = Object.fromEntries(
    categories.map((item) => [
      item,
      item === 'Everything'
        ? products.length
        : products.filter((product) => getProductCategory(product) === item).length,
    ]),
  )
  const filtered = products.filter((product) => {
    const searchable = normalizeSearchText([
      product.name,
      product.garment_type,
      product.description,
      product.search_tags.join(' '),
      product.colors.join(' '),
      product.product_id,
    ].join(' '))
    const queryTerms = normalizeSearchText(deferredSearch).split(/\s+/).filter(Boolean)
    const matchesSearch = queryTerms.every((term) => searchable.includes(term))
    return matchesSearch && (category === 'Everything' || getProductCategory(product) === category)
  })

  return (
    <div className="catalogue-page">
      <section className="catalogue-intro"><p className="eyebrow">THE CAMPUS CUSTOMS COLLECTION</p><h1>Find your <em>favorite.</em></h1><p>Well-loved layers, team-day staples and little bits of Yale to take along.</p></section>
      <div className="catalogue-toolbar">
        <div className="filter-row" aria-label="Filter by product category">{categories.map((item) => <button key={item} className={`filter-chip ${category === item ? 'active' : ''}`} aria-pressed={category === item} onClick={() => { setCategory(item); setSearch(''); setAppliedSearch('') }}><span>{item}</span><span className="filter-count">{categoryCounts[item]}</span></button>)}</div>
        <form className="search-field" role="search" onSubmit={(event) => { event.preventDefault(); setAppliedSearch(search.trim()) }}>
          <button className="search-submit" type="submit" aria-label="Search collection"><Search size={17} /></button>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the collection" aria-label="Search products" />
          {search && <button className="clear-search" type="button" aria-label="Clear search" onClick={() => { setSearch(''); setAppliedSearch('') }}><X size={15} /></button>}
        </form>
      </div>
      <div className="catalogue-count"><span>{loading ? 'Gathering the collection…' : `${filtered.length} pieces`}</span><span>Selected for campus & beyond</span></div>
      {error ? <ApiNotice error={error} /> : <ProductGrid products={filtered} loading={loading} error="" />}
      {!loading && !error && filtered.length === 0 && <div className="empty-state"><p>No pieces found.</p><button onClick={() => { setSearch(''); setCategory('Everything') }}>Clear filters</button></div>}
    </div>
  )
}

function getProductCategory(product: Product) {
  const garmentType = `${product.garment_type} ${product.name}`.toLowerCase()
  if (/(pullover|crewneck)/.test(garmentType)) return 'Sweaters & Sweatshirts'
  if (/(jacket|bomber|coat|windbreaker)/.test(garmentType)) return 'Jackets'
  if (/(hood|hoodie)/.test(garmentType)) return 'Hoodies'
  if (/(t-?shirt|tee|performance shirt|short-sleeve|long-sleeve)/.test(garmentType)) return 'T-shirts'
  return 'Sweaters & Sweatshirts'
}

function ProductGrid({ products, loading, error }: { products: Product[]; loading: boolean; error: string }) {
  if (error) return <ApiNotice error={error} />
  if (loading) return <div className="loading-grid">{Array.from({ length: 4 }, (_, index) => <div className="skeleton" key={index} />)}</div>
  return <div className="product-grid">{products.map((product, index) => <ProductCard product={product} index={index} key={product.product_id} />)}</div>
}

function ProductCard({ product, index = 0, compact = false }: { product: Product; index?: number; compact?: boolean }) {
  const inStock = product.sizes.some((size) => size.quantity > 0)
  return (
    <Link className={`product-card ${compact ? 'product-card-compact' : ''}`} to={`/products/${product.product_id}`}>
      <div className={`product-image image-tone-${index % 4}`}><img src={imageSource(product.image_url)} alt={product.name} loading="lazy" /><span className="product-index">{String(index + 1).padStart(2, '0')}</span><span className="quick-view"><span>View piece</span><ArrowRight size={15} /></span>{!inStock && <span className="stock-ribbon">SOLD OUT</span>}</div>
      <div className="product-meta"><div><span className="product-category">{product.garment_type}</span><h3>{product.name}</h3></div><span className="product-price">{money(product.price)}</span></div>
      <p className="product-excerpt">{excerpt(product.description)}</p>
    </Link>
  )
}

function ProductPage({ products, loading, onAdd }: { products: Product[]; loading: boolean; onAdd: () => void }) {
  const { productId } = useParams()
  const product = products.find((item) => item.product_id === productId)
  const navigate = useNavigate()
  const [size, setSize] = useState('')
  const [added, setAdded] = useState(false)
  const [error, setError] = useState('')

  if (loading) return <div className="product-detail-loading">Loading the good stuff…</div>
  if (!product) return <NotFound />
  const stock = product.sizes.find((item) => item.size === size)?.quantity ?? 0
  const availableSizes = product.sizes.filter((item) => item.quantity > 0)
  const canAdd = Boolean(size) && stock > 0

  function addToBag() {
    if (!canAdd) {
      setError(size ? 'That size is currently out of stock.' : 'Choose a size to continue.')
      return
    }
    onAdd()
    setAdded(true)
    setError('')
  }

  return (
    <div className="product-detail-page">
      <button className="back-link" onClick={() => navigate(-1)}><ArrowLeft size={15} /> Back to the collection</button>
      <div className="product-detail-layout">
        <div className="detail-image-area"><img src={imageSource(product.image_url)} alt={product.name} /><span className="detail-image-note">CAMPUS CUSTOMS / NEW HAVEN</span></div>
        <div className="detail-copy"><p className="eyebrow">{product.garment_type.toUpperCase()} · CC COLLECTION</p><h1>{product.name}</h1><p className="detail-price">{money(product.price)}</p><div className="detail-rule" /><p className="detail-description">{product.description}</p>
          {product.colors.length > 0 && <div className="detail-colors"><span className="field-label">COLOR NOTES</span><p>{product.colors.join(' / ')}</p></div>}
          <div className="size-heading"><span className="field-label">SELECT A SIZE</span><span className="size-guide">A relaxed, everyday fit</span></div>
          <div className="size-options">{product.sizes.map((item) => <button key={item.size} className={`size-button ${size === item.size ? 'selected' : ''} ${item.quantity === 0 ? 'unavailable' : ''}`} onClick={() => { setSize(item.size); setError('') }} disabled={item.quantity === 0} aria-label={`${item.size}, ${item.quantity > 0 ? `${item.quantity} available` : 'sold out'}`} title={item.quantity === 0 ? 'Sold out' : `${item.quantity} in stock`}>{item.size}{item.quantity === 0 && <span className="sr-only"> sold out</span>}</button>)}</div>
          <p className={`availability ${size && stock > 0 ? 'available' : ''}`}>{size ? stock > 0 ? `${stock} in stock in ${size}` : `Sold out in ${size}` : availableSizes.length ? 'Choose a size to see availability' : 'Currently sold out'}</p>
          <button className={`button button-dark add-button ${added ? 'added' : ''}`} onClick={addToBag} disabled={!availableSizes.length}>{added ? <>Added to bag <Check size={17} /></> : <>Add to bag <ShoppingBag size={17} /></>}</button>
          {error && <p className="form-error">{error}</p>}
          <div className="detail-footnote"><Heart size={16} /><span>Made for the walk across campus, and wherever you go after.</span></div>
        </div>
      </div>
    </div>
  )
}

function AboutPage() {
  return (
    <div className="about-page">
      <section className="about-hero"><p className="eyebrow">A NOTE FROM NEW HAVEN</p><h1>Campus has a way<br />of <em>staying with you.</em></h1><p>Even after the last class, the final point, or the ferry back.</p></section>
      <section className="about-body"><div className="about-number">CC<br /><span>01 / 26</span></div><div className="about-copy"><h2>We believe the best souvenirs are the ones that <em>get worn.</em></h2><p>Campus Customs is for people who like their school spirit lived-in: a familiar crewneck for a brisk walk down Chapel Street, a team layer for a match that runs long, a proper sweatshirt for the ride north when the first snow sticks.</p><p>We built this little corner of the internet around the things that make a place feel like yours. Yale is the starting point; the good stories happen everywhere after.</p><p>Think squash before lunch. A late train on Friday. A Vineyard weekend with one more layer than the forecast promised. We’ll bring the sweatshirt.</p><Link className="button button-dark" to="/products">Explore the collection <ArrowRight size={16} /></Link></div></section>
      <section className="about-signoff"><span>NEW HAVEN, CONNECTICUT</span><p>For the place you came from.<br /><em>And all the places you’re going.</em></p><Link to="/products" aria-label="Shop products"><ArrowRight size={18} /></Link></section>
    </div>
  )
}

function AccountPage({ mode, onAuthenticated }: { mode: 'login' | 'create'; onAuthenticated: (user: User) => void }) {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const creating = mode === 'create'
  const navigate = useNavigate()

  async function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (creating && password !== confirmPassword) {
      setError('Those passwords do not match. Please check and try again.')
      return
    }
    setBusy(true)
    try {
      const response = await fetch(`${API_URL}/api/auth/${creating ? 'register' : 'login'}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creating
          ? { first_name: firstName, last_name: lastName, email, password }
          : { email, password }),
      })
      const result = await response.json() as User | { detail?: string | { msg: string }[] }
      if (!response.ok) {
        const detail = 'detail' in result ? result.detail : undefined
        setError(Array.isArray(detail) ? detail.map((item) => item.msg).join(' ') : detail || 'We could not complete that request.')
        return
      }
      onAuthenticated(result as User)
      navigate('/')
    } catch {
      setError('We could not reach the shop. Please try again in a moment.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="account-page"><div className="account-art"><div className="account-stamp">CC<span>NEW HAVEN<br />SINCE ALWAYS</span></div><p>Good company.<br /><em>Good campus.</em></p></div><div className="account-form-wrap"><p className="eyebrow">{creating ? 'JOIN THE CLUB' : 'WELCOME BACK'}</p><h1>{creating ? 'Make yourself at home.' : 'Good to see you.'}</h1><p className="account-subtitle">{creating ? 'A few details and you’re in.' : 'Your campus favorites are right where you left them.'}</p><form className="account-form" onSubmit={submitAccount}>{creating && <><label>First name<input value={firstName} onChange={(event) => setFirstName(event.target.value)} required autoComplete="given-name" placeholder="Alex" maxLength={80} /></label><label>Last name<input value={lastName} onChange={(event) => setLastName(event.target.value)} required autoComplete="family-name" placeholder="Morgan" maxLength={80} /></label></>}<label>Email address<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required autoComplete="email" placeholder="you@example.com" maxLength={254} /></label><label>Password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required autoComplete={creating ? 'new-password' : 'current-password'} placeholder={creating ? 'At least 12 characters' : 'Your password'} minLength={creating ? 12 : 1} maxLength={256} /></label>{creating && <label>Confirm password<input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} type="password" required autoComplete="new-password" placeholder="Enter your password again" minLength={12} maxLength={256} /></label>}{error && <p className="auth-error" role="alert">{error}</p>}<button className="button button-dark form-submit" type="submit" disabled={busy}>{busy ? 'One moment…' : creating ? 'Create my account' : 'Log in'} <ArrowRight size={16} /></button></form><p className="account-switch">{creating ? 'Already have an account?' : 'New around here?'} <Link to={creating ? '/login' : '/create-account'}>{creating ? 'Log in' : 'Create an account'}</Link></p></div></div>
  )
}

function ChatWidget({ isOpen, userId, onToggle }: { isOpen: boolean; userId: number | null; onToggle: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: 'assistant', text: 'Hi there. Looking for a campus classic or a weekend layer?' }])
  const [draft, setDraft] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const { pathname } = useLocation()
  const productId = pathname.match(/^\/products\/([^/]+)$/)?.[1]

  useEffect(() => {
    if (userId === null) {
      setMessages([{ role: 'assistant', text: 'Hi there. Looking for a campus classic or a weekend layer?' }])
    }
  }, [userId])

  useEffect(() => {
    if (!isOpen) return
    let active = true
    setHistoryLoaded(false)
    fetch(`${API_URL}/api/chat/history`, { credentials: 'include' })
      .then((response) => response.ok ? response.json() as Promise<ChatHistoryPayload> : null)
      .then((payload) => {
        if (!active) return
        if (payload?.authenticated) {
          setMessages(payload.messages.map((message) => ({
            role: message.role,
            text: message.content,
            products: message.products,
          })))
        }
        setHistoryLoaded(true)
      })
      .catch(() => { if (active) setHistoryLoaded(true) })
    return () => { active = false }
  }, [isOpen, userId])

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || isSending) return
    setError('')
    setIsSending(true)
    const history = messages.slice(-8).map(({ role, text }) => ({ role, content: text }))
    setMessages((current) => [...current, { role: 'user', text: message }])
    setDraft('')
    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history, page_context_product_id: productId }),
      })
      const result = await response.json() as { reply?: string; products?: Product[]; detail?: string }
      if (!response.ok) throw new Error(result.detail || 'The shop assistant could not reply just now.')
      setMessages((current) => [...current, { role: 'assistant', text: result.reply || 'I could not put together a reply. Please try again.', products: result.products || [] }])
    } catch (sendError) {
      const messageText = sendError instanceof Error ? sendError.message : 'The shop assistant could not reply just now.'
      setError(messageText)
      setMessages((current) => [...current, { role: 'assistant', text: 'I’m having trouble reaching the shop desk just now. Please try again in a moment.' }])
    } finally {
      setIsSending(false)
    }
  }
  return (
    <div className="chat-widget">
      {isOpen && <section className="chat-panel" aria-label="Campus Customs chat"><div className="chat-header"><div><span className="chat-status" /><strong>A little help?</strong><small>Campus Customs · New Haven</small></div><button className="icon-button" onClick={onToggle} aria-label="Close chat"><X size={19} /></button></div><div className="chat-messages" aria-live="polite">{messages.map((message, index) => <div className={`chat-entry ${message.role}`} key={`${index}-${message.text}`}><p className={`chat-message ${message.role}`}>{message.text}</p>{message.products?.length ? <div className="chat-product-grid">{message.products.map((product, productIndex) => <ProductCard product={product} index={productIndex} compact key={product.product_id} />)}</div> : null}</div>)}{isSending && <p className="chat-message assistant chat-thinking">Checking the collection…</p>}</div>{error && <p className="chat-inline-error" role="status">{error}</p>}<form className="chat-input" onSubmit={sendMessage}><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={historyLoaded ? 'Ask us something' : 'Opening the shop desk…'} aria-label="Chat message" maxLength={1200} disabled={isSending || !historyLoaded} /><button type="submit" aria-label="Send message" disabled={!draft.trim() || isSending || !historyLoaded}><Send size={17} /></button></form><div className="chat-privacy">Shopping help only. Please don’t share passwords or payment details.</div></section>}
      <button className={`chat-launcher ${isOpen ? 'chat-active' : ''}`} onClick={onToggle} aria-label={isOpen ? 'Close chat' : 'Open chat'}>{isOpen ? <X size={19} /> : <MessageCircle size={20} />}<span>{isOpen ? 'Close' : 'Need a hand?'}</span></button>
    </div>
  )
}

function ApiNotice({ error }: { error: string }) {
  return <div className="api-notice"><strong>The collection is having a moment.</strong><p>{error} Start the FastAPI service in <code>homework/4/backend</code> and refresh.</p></div>
}

function NotFound() {
  return <section className="not-found"><p className="eyebrow">THAT PAGE IS OFF CAMPUS</p><h1>Nothing to see<br /><em>down this path.</em></h1><Link className="button button-dark" to="/">Back to the shop <ArrowRight size={16} /></Link></section>
}

function ArrowUpRightIcon() { return <ArrowRight size={14} className="diagonal-arrow" /> }

export default App
